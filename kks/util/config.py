import re
from pathlib import Path
from typing import List, Optional

import click

from kks.util.common import find_workspace, find_problem_rootdir


target_file = 'targets.yaml'

global_comment = '# This is the default config file, it is used in any subdirectory of the workspace.\n'\
                 '# You can modify the default target (the changes will be applied only in this workspace).\n'\
                 '# Also, you can add/overwrite targets by creating another "targets.yaml" file in your working directory.\n'\
                 '\n'


class Target:
    class Options:
        """A class containing type hints for all parsed options."""
        compiler: Optional[str]
        cpp_compiler: Optional[str]
        std: Optional[str]
        cpp_std: Optional[str]
        flags: Optional[List[str]]
        files: Optional[List[str]]
        libs: Optional[List[str]]
        asm64bit: Optional[bool]
        default_asan: Optional[bool]
        out: Optional[str]

        @classmethod
        def names(cls):
            return cls.__annotations__.keys()

    def __init__(self, name, settings):
        self.name = name
        self.need_default = False
        self.parent = None

        for opt_name in self.Options.names():
            value = settings.get(opt_name)
            setattr(self, opt_name, value)
            # option is not set or the list contains "DEFAULT" as first item
            # if the list is empty, we shouldn't replace it (e.g. if this target excludes all libs)
            if value is None or (isinstance(value, list) and value and value[0] == 'DEFAULT'):
                self.need_default = True

    def __str__(self):
        options = [
            f'{opt_name}={getattr(self, opt_name)}' for opt_name in self.Options.names()
        ]
        return f'Target("{self.name}", {", ".join(options)}")'

    def set_parent(self, parent: Optional['Target']):
        """Insert a target into the inheritance chain as the parent of this target."""
        if parent is not None:
            parent.parent = self.parent
        self.parent = parent

    def resolve_options(self, problem):
        """Replace macros and pull missing options from parents."""
        if self.need_default:
            assert self.parent is not None
            self.parent.resolve_options(problem)

        def modify(x):
            return x.replace('TASKNAME', problem)

        def modify_list(lst):
            if len(lst) == 0:
                return lst
            if lst[0] == 'DEFAULT':
                assert self.parent is not None
                default = getattr(self.parent, opt_name)
                lst = default + lst[1:]
            return [modify(e) for e in lst]

        for opt_name in self.Options.names():
            opt = getattr(self, opt_name)
            if opt is None:
                assert self.parent is not None
                opt = getattr(self.parent, opt_name)
            if isinstance(opt, list):
                opt = modify_list(opt)
            elif isinstance(opt, str):
                opt = modify(opt)
            setattr(self, opt_name, opt)


def check_version(cfg_file, cfg, new_version, is_global=False):
    if cfg.get('__version__', new_version) == new_version:
        return

    old_version = cfg['__version__']
    click.echo(
        click.style(str(cfg_file.absolute()), fg='blue', bold=True) +
        click.style(
            ' is outdated. You can run "kks init --config=update"'
            ' if you want to update the default target manually (see README on Github)',
            fg='yellow'
        )
    )
    click.pause()
    cfg_file.write_text(
        re.sub(
            rf'^(__version__: +){old_version}',
            rf'\g<1>{new_version}',
            cfg_file.read_text(),
            1, re.M
        )
    )


def find_target(name):
    import yaml

    def load_config(config_file):
        with config_file.open('r') as f:
            try:
                config = yaml.safe_load(f)
                return config
            except yaml.parser.ParserError:
                click.secho(f'Cannot parse {config_file.absolute()}', fg='red', err=True)
                return None

    def get_target(config, target_name):
        if config is None:
            return None
        if target_name in config:
            return Target(target_name, config[target_name])
        return None

    # we don't use pkg_resources, because it takes 300+ ms to load
    package_cfg = load_config(Path(__file__).parents[1] / 'data' / target_file)

    # package_default should have all fields set
    package_default = Target('default', package_cfg['default'])

    cwd = Path.cwd()
    workspace = find_workspace()
    rootdir = find_problem_rootdir()
    problem = '{}-{}'.format(*rootdir.parts[-2:]) if rootdir is not None else 'sm00-0'

    if workspace is not None:
        root_file = workspace / target_file  # we load root config even if we won't need it
        root_cfg = load_config(root_file) if root_file.is_file() else None
        if root_cfg is not None:
            check_version(root_file, root_cfg, package_cfg['__version__'], True)
    else:
        root_cfg = None

    if workspace is None or cwd != workspace:
        local_file = cwd / target_file
        local_cfg = load_config(local_file) if local_file.is_file() else None
        if local_cfg is not None:
            check_version(local_file, local_cfg, package_cfg['__version__'])
    else:
        local_cfg = None

    # Any target except package_default may have missing fields (e.g. an otdated custom target file).
    # In this case we need to inherit from package_default.
    # As a side effect, custom default targets are able to use the DEFAULT macro.
    # The result of using DEFAULT in a default target is undefined.

    # Inheritance chain:
    # local_default -> [[root_default] -> package_default] -> None
    # local_non_default -> [[local_default or root_default] -> package_default] -> None
    local_target = get_target(local_cfg, name)
    if local_target is not None:
        if local_target.need_default:
            local_target.set_parent(package_default)
            if name == 'default':
                custom_default = get_target(root_cfg, 'default')
            else:
                custom_default = get_target(local_cfg, 'default') or get_target(root_cfg, 'default')
            if custom_default is not None:
                local_target.set_parent(custom_default)
        local_target.resolve_options(problem)
        return local_target

    # Inheritance chain:
    # root_default -> [package_default] -> None
    # root_non_default -> [[root_default] -> package_default] -> None
    root_target = get_target(root_cfg, name)
    if root_target is not None:
        if root_target.need_default:
            root_target.set_parent(package_default)
            if name != 'default':
                root_default = get_target(root_cfg, 'default')
                if root_default is not None:
                    root_target.set_parent(root_default)
        root_target.resolve_options(problem)
        return root_target

    if name == 'default':
        package_target = package_default
    else:
        package_target = get_target(package_cfg, name)
        if package_target is None:
            # not found
            return None
        if package_target.need_default:
            package_target.set_parent(package_default)

    package_target.resolve_options(problem)
    return package_target
