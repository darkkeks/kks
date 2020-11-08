import click

from kks.ejudge import ejudge_summary, ejudge_sample
from kks.util import get_valid_session, load_links, find_workspace


@click.command()
def sync():
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
                click.secho(f'Directory {task_dir.relative_to(workspace)} already exists, skipping',
                            fg='yellow', err=True)
            else:
                click.secho(f'File {task_dir.relative_to(workspace)} exists, skipping',
                            fg='red', err=True)
            continue

        click.secho('Creating directories for task ' + click.style(problem.name, fg='blue', bold=True), err=True)

        task_dir.mkdir(parents=True, exist_ok=True)

        main = task_dir / 'main.c'
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

    click.secho('Sync done!', fg='green')
