from pathlib import Path

import click

from kks.util.common import find_workspace, get_hidden_dir


@click.command()
@click.option('-f', '--force', is_flag=True)
def init(force):
    """Initialize kks workspace in current directory."""

    if not force:
        workspace = find_workspace()
        if workspace is not None:
            click.secho(f'Found workspace in directory {workspace}\n'
                        f'If you are sure you want to create workspace here, specify --force', fg='yellow')
            return

    path = Path()
    file = path / '.kks-workspace'

    if file.exists():
        if file.is_file():
            click.secho('Workspace already exists', fg='green')
        elif file.is_dir():
            click.secho('Workspace marker is a directory (.kks-workspace)', fg='yellow')
        else:
            click.secho('Workspace marker is an unknown file type (.kks-workspace)', fg='yellow')
        return
    else:
        file.write_text("This file is used to find kks workspace.\n")

    hidden = get_hidden_dir(path)
    if hidden.exists():
        if hidden.is_dir():
            click.secho(f'The directory for hidden contests already exists ({hidden.relative_to(path)})', fg='yellow')
        else:
            click.secho(f'{hidden.relative_to(path)} exists and is not a directory, "kks (un)hide" may break!', fg='red')
    else:
        hidden.mkdir()

    click.secho(f'Initialized workspace in directory {path}', fg='green')
