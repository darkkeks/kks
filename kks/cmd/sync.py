import click

from kks.ejudge import Status, ejudge_summary, ejudge_sample, ejudge_submissions
from kks.util import get_valid_session, load_links, find_workspace


def save_needed(submissions, sub_dir, session):
    def prefix(submission):
        return f'{submission.id:05d}'
    def format_filename(submission):
        return f'{prefix(submission)}-{submission.short_status()}.c'

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
        file = sub_dir / format_filename(sub)
        if len(old) == 1:
            if old[0].name != file.name:
                old[0].rename(file)
            continue
        source = session.get(sub.href)
        with open(file, 'wb') as f:
            f.write(source.content)


def sync_code(problem, task_dir, session):
    sub_dir = task_dir / 'submissions'
    if sub_dir.exists():
        if not task_dir.is_dir():
            click.secho(f'File {sub_dir.relative_to(workspace)} exists, skipping',
                        fg='red', err=True)
            return
    else:
        sub_dir.mkdir(parents=True, exist_ok=True)
    submissions = ejudge_submissions(problem, session)
    if submissions:
        save_needed(submissions, sub_dir, session)


@click.option('--code', is_flag=True, default=False,
              help='Download latest submitted solutions')
@click.command()
def sync(code):
    """Parse problems from ejudge"""

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

    for problem in problems:
        contest, number = problem.short_name.split('-')

        task_dir = workspace / contest / number

        if task_dir.exists():
            if task_dir.is_dir():
                if code:
                    click.secho('Syncing submissions for ' + click.style(problem.name, fg='blue', bold=True))
                    sync_code(problem, task_dir, session)
                else:
                    click.secho(f'Directory {task_dir.relative_to(workspace)} already exists, skipping',
                                fg='yellow', err=True)
            else:
                click.secho(f'File {task_dir.relative_to(workspace)} exists, skipping',
                            fg='red', err=True)
            continue

        click.secho('Creating directories for task ' + click.style(problem.name, fg='blue', bold=True), err=True)

        task_dir.mkdir(parents=True, exist_ok=True)

        main = task_dir / f'{problem.short_name}.c'
        main.touch()

        gen = task_dir / 'gen.py'
        gen.touch()

        solve = task_dir / 'solve.py'
        solve.touch()

        tests_dir = task_dir / 'tests'
        tests_dir.mkdir(exist_ok=True)

        input_data, output_data = ejudge_sample(problem.href, session)

        if input_data is not None:
            with (tests_dir / '000.in').open('w') as f:
                f.write(input_data)

        if output_data is not None:
            output_data += '\n'
            with (tests_dir / '000.out').open('w') as f:
                f.write(output_data)

        if code:
            click.secho('Syncing submissions')
            sync_code(problem, task_dir, session)

    click.secho('Sync done!', fg='green')
