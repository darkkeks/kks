from cgi import parse_header
from mimetypes import guess_extension
from os import environ

import click

from kks.ejudge import Status, ejudge_summary, ejudge_statement, ejudge_submissions, ejudge_report
from kks.util import get_valid_session, load_links, find_workspace, get_task_dir, write_contests


class Choice2(click.Choice):
    """ for nice help message """
    def get_metavar(self, param):
        if len(self.choices) == 1:
            return self.choices[0]
        return "[{}]".format("|".join(self.choices))


# classes to create a flag with optional value, see https://stackoverflow.com/a/44144098
# click 8.0 should support something like this (https://github.com/pallets/click/issues/549)
class FlagOption(click.Option):
    """ Mark this option as getting a _opt option """
    is_optflag = True


class OptFlagOption(click.Option):
    """ Fix the help for the _opt suffix """
    def get_help_record(self, ctx):
        help = super().get_help_record(ctx)
        return (help[0].replace('_opt ', '='),) + help[1:]

    def get_error_hint(self, ctx):
        hint = super().get_error_hint(ctx)
        return hint.replace('_opt', '')


class OptFlagCommand(click.Command):
    """ Command with support for flags with values """
    def parse_args(self, ctx, args):
        """ Translate any flag= to flag_opt= as needed """
        options = [o for o in ctx.command.params
                   if getattr(o, 'is_optflag', None)]
        prefixes = {p for p in sum([o.opts for o in options], [])
                    if p.startswith('--')}
        for i, a in enumerate(args):
            a = a.split('=')
            if a[0] in prefixes and len(a) > 1:
                a[0] += '_opt'
                args[i] = '='.join(a)

        return super().parse_args(ctx, args)


def save_needed(submissions, sub_dir, session, full_sync):
    def prefix(submission):
        return f'{submission.id:05d}'

    def format_stem(submission):
        return f'{prefix(submission)}-{submission.short_status()}'

    def get_extension(resp):
        mimetype, _ = parse_header(resp.headers.get('Content-Type', ''))
        mimetype = mimetype.lower()
        if mimetype == 'text/plain':
            return '.c'
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

        file = file.with_suffix(get_extension(resp))

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
        save_needed(problem_subs, sub_dir, session, full_sync)


@click.command(cls=OptFlagCommand)
@click.option('--code', cls=FlagOption, is_flag=True,
              help='Download latest submitted solutions')
@click.option('--code_opt', cls=OptFlagOption, type=Choice2(['all']),
              help='Download all submissions')
@click.option('-f', '--force', is_flag=True, default=False,
              help='Force sync existing tasks')
@click.argument('filters', nargs=-1)
def sync(code, code_opt, force, filters):
    """Parse problems from ejudge

    If any FILTERS are specified, sync only tasks with matching prefixes/names
    """

    workspace = find_workspace()

    if workspace is None:
        click.secho('You have to run sync under kks workspace (use "kks init" to create one)', fg='red', err=True)
        return

    session = get_valid_session()
    if session is None:
        return

    links = load_links()
    if links is None:
        click.secho('Auth data is invalid, use "kks auth" to authorize', fg='red', err=True)
        return

    problems = ejudge_summary(links, session)

    code_all = code_opt == 'all'
    code = code or code_all
    if code:
        submissions = ejudge_submissions(links, session)

    md_width = int(environ.get('MDWIDTH', '100'))

    contests = set()
    bad_contests = set()
    total_problems = 0
    old_problems = 0
    new_problems = 0

    for problem in problems:
        if filters and not any(problem.short_name.startswith(f) for f in filters):
            continue
        total_problems += 1
        contest, number = problem.short_name.split('-')
        contests.add(contest)
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

        main = task_dir / f'{problem.short_name}.c'
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

        statement = ejudge_statement(problem.href, session)

        with (task_dir / 'statement.html').open('w') as f:
            f.write(statement.html())
        with (task_dir / 'statement.md').open('w') as f:
            f.write(statement.markdown(width=md_width))

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
