from pathlib import Path

import click

from kks.util.click import OptFlagCommand, FlagOption, OptFlagOption, Choice2
from kks.util.common import find_workspace, get_hidden_dir, format_file
from kks.util.config import target_file, global_comment
from kks.util.storage import Config


@click.command(cls=OptFlagCommand)
@click.option('-f', '--force', is_flag=True)
@click.option('-c', '--config', cls=FlagOption, is_flag=True,
              help=f'Create {target_file} in current directory and exit')
@click.option('--config_opt', cls=OptFlagOption, type=Choice2(['update', 'global']),
              help='Create a copy of config for manual updating '
                   'or create config in the root dir of workspace')  # TODO multiline help?
def init(force, config, config_opt):
    """Initialize kks workspace in current directory."""

    path = Path()
    file = path / '.kks-workspace'
    old_workspace = False

    if config or config_opt:
        if config_opt == 'global':
            workspace = find_workspace()
            if workspace is None:
                click.secho(
                    'Current directory is not in a kks workspace.'
                    'To use "global" option, you need to cd into an existing workspace '
                    'or run "kks init"',
                    fg='red'
                )
                return
            path = workspace
            is_global = True
        else:
            is_global = file.exists()
        create_config(path, is_global, config_opt == 'update', force)
        return

    if not force:
        workspace = find_workspace()
        if workspace is not None:
            click.secho(
                f'Found workspace in directory {workspace}\n'
                'If you are sure you want to create workspace here, specify --force',
                fg='yellow'
            )
            return

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
            click.secho(
                f'The directory for hidden contests already exists ({hidden.relative_to(path)})\n',
                fg='yellow'
            )
        else:
            click.secho(
                f'{hidden.relative_to(path)} exists and is not a directory, '
                '"kks (un)hide" may break!\n',
                fg='red'
            )
    else:
        hidden.mkdir()

    write_cmakelists(path)

    action = 'Updated' if old_workspace else 'Initialized'
    click.secho(f'{action} workspace in directory {path.absolute()}', fg='green', bold=True)


def create_config(directory, is_global, update, force):
    from pkg_resources import resource_stream
    file = directory / target_file
    if update:
        file = file.with_suffix(file.suffix + '.default')
    else:
        if file.exists():
            if not file.is_file():
                click.secho(
                    f'"{file}" exists and is not a file, '
                    'you will need to replace it to create custom targets',
                    fg='red'
                )
                return
            elif not force:
                click.secho(
                    f'The file {file} already exists. '
                    'Use --force to overwrite it or --config=update to create a copy',
                    fg='yellow'
                )
                return

    data = resource_stream('kks', f'data/{target_file}').read().decode()
    if is_global:
        data = global_comment + data
    file.write_text(data)

    if update:
        click.secho('New default targets are written to ', fg='green', nl=False)
        click.secho(format_file(file), nl=False)
        click.secho(', you can merge it with ', fg='green', nl=False)
        click.secho(format_file(file.with_name(target_file)), nl=False)
        click.secho(' manually', fg='green')
    else:
        click.secho('Default targets are written to ', fg='green', nl=False)
        click.secho(format_file(file))
        click.secho('The config file is not updated automatically.', bold=True)


def write_cmakelists(directory):
    config = Config()
    if not config.options.generate_cmakelists:
        return

    click.secho('Writing CMakeLists.txt...', fg='green')

    path = directory / 'CMakeLists.txt'

    if path.exists():
        return

    path.write_text('''cmake_minimum_required(VERSION 3.10)

project(caos C ASM)

# Function to recursively add subdirectories
function(add_subdirectories_recursively dir)
    if(IS_DIRECTORY ${dir})
        file(GLOB sub_dirs RELATIVE ${dir} ${dir}/*)
        foreach(sub_dir ${sub_dirs})
            if(IS_DIRECTORY ${dir}/${sub_dir})
                if(EXISTS ${dir}/${sub_dir}/CMakeLists.txt)
                    # Prepend the relative path from the source directory to the current directory
                    get_filename_component(full_dir "${dir}/${sub_dir}" REALPATH BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
                    file(RELATIVE_PATH rel_dir "${CMAKE_CURRENT_SOURCE_DIR}" "${full_dir}")
                    add_subdirectory(${rel_dir})
                endif()
                add_subdirectories_recursively(${dir}/${sub_dir})
            endif()
        endforeach()
    endif()
endfunction()


# Call the function on the current source directory
add_subdirectories_recursively(${CMAKE_CURRENT_SOURCE_DIR})
''')
