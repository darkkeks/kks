from enum import Enum
from mimetypes import guess_extension
from shutil import rmtree

import click

from kks.ejudge import Status, ejudge_summary, ejudge_submissions, ejudge_report
from kks.util.click import OptFlagCommand, FlagOption, OptFlagOption, Choice2
from kks.util.common import find_workspace, get_task_dir, write_contests, parse_content_type
from kks.util.ejudge import EjudgeSession
from kks.util.storage import Config


class CodeSync(Enum):
    ALL = 'all'
    REJECTS = 'rejects'


def save_needed(problem, submissions, sub_dir, session, mode: CodeSync):
    def prefix(submission):
        return f'{submission.id:05d}'

    def format_stem(submission):
        return f'{prefix(submission)}-{submission.short_status()}'

    def get_extension(submission, resp):
        mimetype, _ = parse_content_type(resp.headers.get('Content-Type', ''))
        mimetype = mimetype.lower()
        if mimetype == 'text/plain':
            return submission.suffix()
        elif mimetype == 'application/x-gzip':
            return '.gz'
        else:
            suf = guess_extension(mimetype)
            if suf is None or suf == '.':
                return ''
            return suf

    if mode == CodeSync.ALL:
        needed = submissions
    elif mode == CodeSync.REJECTS:
        needed = [sub for sub in submissions if sub.status == Status.REJECTED]
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

            # may need to load the report (PR -> RJ: comments, running -> partial: failed tests)
            if sub.status not in [Status.PARTIAL, Status.REJECTED]:
                # Comments for existing PR->OK, PR->IG submissions are not synced.
                # Also, comments without status change are not updated (see stem check above)
                # TODO check new comments on Clars page?
                continue

        resp = session.get(sub.source)

        file = file.with_suffix(get_extension(sub, resp))

        source = resp.content
        if sub.status in [Status.PARTIAL, Status.REJECTED]:
            report = ejudge_report(sub.report, session)
            source = report.as_comment().encode() + source

        with open(file, 'wb') as f:
            f.write(source)


def sync_code(problem, task_dir, submissions, session, mode: CodeSync):
    sub_dir = task_dir / 'submissions'
    if sub_dir.exists():
        if not sub_dir.is_dir():
            click.secho(f'File {sub_dir.relative_to(find_workspace())} exists, skipping',
                        fg='red', err=True)
            return
    else:
        sub_dir.mkdir(parents=True, exist_ok=True)
    problem_subs = submissions.get(problem.short_name, [])
    if problem_subs:
        save_needed(problem, problem_subs, sub_dir, session, mode)


def sync_attachments(problem, dest_dir, session):
    attachments = problem.attachments()
    dest_dir_exists = dest_dir.exists()
    if dest_dir_exists and not dest_dir.is_dir():
        if attachments:
            click.secho(
                f'File {dest_dir.relative_to(find_workspace())} exists, '
                'skipping attachment sync',
                fg='red', err=True
            )
        # Don't warn if the attachment list is empty
        return

    if dest_dir_exists:
        # If an attachment was removed from the statement, it should be deleted.
        # Remove all attachments, existing ones will be resynced anyway.
        rmtree(dest_dir)

    if not attachments:
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    for att_name, url in attachments.items():
        att_path = dest_dir / att_name
        page = session.get(url)
        with att_path.open('wb') as f:
            f.write(page.content)


@click.command(short_help='Parse problems from ejudge', cls=OptFlagCommand)
@click.option('--code', cls=FlagOption, is_flag=True,
              help='Download latest submitted solutions')
@click.option('--code_opt', cls=OptFlagOption, type=Choice2(['all', 'rejects']),
              help='Download all / all rejected submissions')
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
        click.secho(
            'You have to run sync under kks workspace (use "kks init" to create one)',
            fg='red', err=True
        )
        return

    config = Config()

    session = EjudgeSession()
    problems = ejudge_summary(session)

    code_sync_mode = CodeSync(code_opt) if code_opt else None
    code = code or code_sync_mode
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
            click.secho(
                'Creating directories for task ' + click.style(problem.name, fg='blue', bold=True)
            )
            task_dir.mkdir(parents=True, exist_ok=True)
        else:
            if not task_dir.is_dir():
                click.secho(
                    f'File {task_dir.relative_to(workspace)} exists, skipping',
                    fg='red', err=True
                )
                continue

            if not force:
                if code:
                    click.secho(
                        'Syncing submissions for ' +
                        click.style(problem.name, fg='blue', bold=True)
                    )
                    sync_code(problem, task_dir, submissions, session, code_sync_mode)
                    new_problems += 1
                else:
                    old_problems += 1
                continue

            click.secho('Resyncing task ' + click.style(problem.name, fg='blue', bold=True))

        new_problems += 1

        problem = problem.get_full(session)

        main = (task_dir / problem.short_name).with_suffix(problem.suffix())
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

        html_statement_path = task_dir / 'statement.html'
        md_statement_path = task_dir / 'statement.md'
        attachments_path = task_dir / 'attachments'

        if config.options.save_html_statements:
            # overwrite only if statement is available
            if problem.statement_available() or not html_statement_path.exists():
                with html_statement_path.open('w') as f:
                    f.write(problem.html())
        elif html_statement_path.is_file():
            html_statement_path.unlink()

        if config.options.save_md_statements:
            if problem.statement_available() or not md_statement_path.exists():
                with md_statement_path.open('w') as f:
                    f.write(problem.markdown(width=md_width))
        elif md_statement_path.is_file():
            md_statement_path.unlink()

        if config.options.save_attachments:
            if problem.statement_available():
                sync_attachments(problem, attachments_path, session)
        elif attachments_path.is_dir():
            rmtree(attachments_path)

        if problem.input_data is not None:
            with (tests_dir / '000.in').open('w') as f:
                f.write(problem.input_data)

        if problem.output_data is not None:
            with (tests_dir / '000.out').open('w') as f:
                f.write(problem.output_data)

        if code:
            click.secho('Syncing submissions')
            sync_code(problem, task_dir, submissions, session, code_sync_mode)

    write_contests(workspace, contests)

    color = 'green' if old_problems + new_problems == total_problems else 'red'
    click.secho('Sync done!', fg='green')
    click.secho(
        f'Synced tasks: {old_problems+new_problems}/{total_problems} ({old_problems} unchanged)',
        fg=color
    )
