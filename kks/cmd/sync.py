from mimetypes import guess_extension
from os import environ

import click

from kks.ejudge import Status, ejudge_summary, ejudge_statement, ejudge_submissions, ejudge_report
from kks.util.click import OptFlagCommand, FlagOption, OptFlagOption, Choice2
from kks.util.common import find_workspace, get_task_dir, write_contests
from kks.util.ejudge import EjudgeSession
from kks.util.storage import Config


def source_suf(problem):
    pref = problem.name.split('/', 1)[0]
    if pref == 'asm':
        return '.S'
    return '.c'


def save_needed(problem, submissions, sub_dir, session, full_sync):
    def prefix(submission):
        return f'{submission.id:05d}'

    def format_stem(submission):
        return f'{prefix(submission)}-{submission.short_status()}'

    def get_extension(problem, resp):
        from cgi import parse_header

        mimetype, _ = parse_header(resp.headers.get('Content-Type', ''))
        mimetype = mimetype.lower()
        if mimetype == 'text/plain':
            return source_suf(problem)
        elif mimetype == 'application/x-gzip':
            return '.gz'
        else:
            suf = guess_extension(mimetype)
            if suf is None or suf == '.':
                return ''
            return suf

    if full_sync:
        needed = submissions
    else:
        ok, review, reject, partial = [], [], [], []
        for sub in submissions:
            if sub.status == Status.OK:
                ok.append(sub)
            elif sub.status == Status.REVIEW:
                review.append(sub)
            elif sub.status == Status.REJECTED:
                reject.append(sub)
            elif sub.status != Status.IGNORED:
                partial.append(sub)

        needed = {submissions[0]}  # always save latest
        # add last solution that passed all tests
        if ok:
            needed.add(ok[0])
        elif review:
            needed.add(review[0])
        elif reject:
            needed.add(reject[0])

    for sub in needed:
        old = list(sub_dir.glob(f'{prefix(sub)}-*'))
        file = sub_dir / format_stem(sub)
        if len(old) == 1:
            # status may change
            if old[0].stem == file.stem:
                continue
            old[0].rename(file.with_suffix(old[0].suffix))
            # may need to load the report
            if sub.status not in [Status.PARTIAL, Status.REJECTED]:
                continue

        resp = session.get(sub.source)

        file = file.with_suffix(get_extension(problem, resp))

        source = resp.content
        if sub.status in [Status.PARTIAL, Status.REJECTED]:
            report = ejudge_report(sub.report, session)
            source = report.as_comment().encode() + source

        with open(file, 'wb') as f:
            f.write(source)


def sync_code(problem, task_dir, submissions, session, full_sync):
    sub_dir = task_dir / 'submissions'
    if sub_dir.exists():
        if not task_dir.is_dir():
            click.secho(f'File {sub_dir.relative_to(find_workspace())} exists, skipping',
                        fg='red', err=True)
            return
    else:
        sub_dir.mkdir(parents=True, exist_ok=True)
    problem_subs = submissions.get(problem.short_name, [])
    if problem_subs:
        save_needed(problem, problem_subs, sub_dir, session, full_sync)


@click.command(short_help='Parse problems from ejudge', cls=OptFlagCommand)
@click.option('--code', cls=FlagOption, is_flag=True,
              help='Download latest submitted solutions')
@click.option('--code_opt', cls=OptFlagOption, type=Choice2(['all']),
              help='Download all submissions')
@click.option('-f', '--force', is_flag=True, default=False,
              help='Force sync existing tasks')
@click.argument('filters', nargs=-1)
def sync(code, code_opt, force, filters):
    """
    Parse problems from ejudge

    If any FILTERS are specified, sync only tasks with matching prefixes/names
    """

    workspace = find_workspace()

    if workspace is None:
        click.secho('You have to run sync under kks workspace (use "kks init" to create one)', fg='red', err=True)
        return

    config = Config()

    session = EjudgeSession()
    problems = ejudge_summary(session)

    code_all = code_opt == 'all'
    code = code or code_all
    if code:
        submissions = ejudge_submissions(session)

    md_width = config.options.mdwidth

    contests = set()
    bad_contests = set()
    total_problems = 0
    old_problems = 0
    new_problems = 0

    for problem in problems:
        contest, number = problem.short_name.split('-')
        contests.add(contest)
        if filters and not any(problem.short_name.startswith(f) for f in filters):
            continue
        total_problems += 1
        if contest in bad_contests:
            continue
        task_dir = get_task_dir(workspace, contest, number)
        contest_dir = task_dir.parent

        if contest_dir.exists() and not contest_dir.is_dir():
            click.secho(f'File {contest_dir.relative_to(workspace)} exists, skipping',
                        fg='red', err=True)
            bad_contests.add(contest)
            continue

        if not task_dir.exists():
            click.secho('Creating directories for task ' + click.style(problem.name, fg='blue', bold=True))
            task_dir.mkdir(parents=True, exist_ok=True)
        else:
            if not task_dir.is_dir():
                click.secho(f'File {task_dir.relative_to(workspace)} exists, skipping', fg='red', err=True)
                continue

            if not force:
                if code:
                    click.secho('Syncing submissions for ' + click.style(problem.name, fg='blue', bold=True))
                    sync_code(problem, task_dir, submissions, session, code_all)
                    new_problems += 1
                else:
                    old_problems += 1
                continue

            click.secho('Resyncing task ' + click.style(problem.name, fg='blue', bold=True))

        new_problems += 1

        main = (task_dir / problem.short_name).with_suffix(source_suf(problem))
        main.touch()

        gen = task_dir / 'gen.py'

        if not gen.exists():
            with gen.open('w') as file:
                file.write('import sys\n'
                           'import random\n'
                           '\n'
                           't = int(sys.argv[1])\n'
                           'random.seed(t)\n')

        solve = task_dir / 'solve.py'
        solve.touch()

        tests_dir = task_dir / 'tests'
        tests_dir.mkdir(exist_ok=True)

        statement = ejudge_statement(problem.href, session)  # TODO use API? (kr contests, see #55)

        html_statement_path = task_dir / 'statement.html'
        md_statement_path = task_dir / 'statement.md'

        if config.options.save_html_statements:
            with html_statement_path.open('w') as f:
                f.write(statement.html())
        elif html_statement_path.is_file():
            html_statement_path.unlink()

        if config.options.save_md_statements:
            with md_statement_path.open('w') as f:
                f.write(statement.markdown(width=md_width))
        elif md_statement_path.is_file():
            md_statement_path.unlink()

        if statement.input_data is not None:
            with (tests_dir / '000.in').open('w') as f:
                f.write(statement.input_data)

        if statement.output_data is not None:
            with (tests_dir / '000.out').open('w') as f:
                f.write(statement.output_data + '\n')

        if code:
            click.secho('Syncing submissions')
            sync_code(problem, task_dir, submissions, session, code_all)

    write_contests(workspace, contests)

    color = 'green' if old_problems + new_problems == total_problems else 'red'
    click.secho('Sync done!', fg='green')
    click.secho(f'Synced tasks: {old_problems+new_problems}/{total_problems} ({old_problems} unchanged)', fg=color)
