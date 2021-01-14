from pathlib import Path
from pkg_resources import resource_stream

import click

from kks.util.common import find_workspace, get_hidden_dir
from kks.util.config import target_file


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
    old_workspace = False

    if file.exists():
        if file.is_file():
            click.secho('Workspace already exists.', fg='green')
            click.secho('Adding missing files...\n', fg='green')
            old_workspace = True
        elif file.is_dir():
            click.secho('Workspace marker is a directory (.kks-workspace)', fg='yellow')
            return
        else:
            click.secho('Workspace marker is an unknown file type (.kks-workspace)', fg='yellow')
            return
    else:
        file.write_text('This file is used to find kks workspace.\n')

    hidden = get_hidden_dir(path)
    if hidden.exists():
        if hidden.is_dir():
            click.secho(f'The directory for hidden contests already exists ({hidden.relative_to(path)})\n', fg='yellow')
        else:
            click.secho(f'{hidden.relative_to(path)} exists and is not a directory, "kks (un)hide" may break!\n', fg='red')
    else:
        hidden.mkdir()

    targets = resource_stream('kks', f'data/{target_file}')
    workspace_targets = path / target_file

    if workspace_targets.exists():
        if workspace_targets.is_file():
            click.secho(f'The file {target_file} already exists', fg='yellow')
        else:
            click.secho(f'"{target_file}" exists and is not a file, you will need to replace it to create custom targets', fg='red')
        workspace_targets = workspace_targets.with_suffix(workspace_targets.suffix + '.default')
        click.secho(f'Saving default targets to "{workspace_targets.name}"\n', fg='green')
    workspace_targets.write_bytes(targets.read())

    action = 'Updated' if old_workspace else 'Initialized'
    click.secho(f'{action} workspace in directory {path.absolute()}', fg='green', bold=True)
