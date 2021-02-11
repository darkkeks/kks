import re
from pathlib import Path

import click

from kks.util.common import find_workspace, find_problem_rootdir, config_directory


target_file = 'targets.yaml'

global_comment = '# This is the default config file, it is used in any subdirectory of the workspace.\n'\
                 '# You can modify the default target (the changes will be applied only in this workspace).\n'\
                 '# Also, you can add/overwrite targets by creating another "targets.yaml" file in your working directory.\n'\
                 '\n'

class Target:
    def __init__(self, name, settings):
        self.name = name
        self.files = settings.get('files')
        self.compiler = settings.get('compiler')
        self.flags = settings.get('flags')
        self.libs = settings.get('libs')
        self.asm64bit = settings.get('asm64bit')
        self.default_asan = settings.get('default_asan')
        self.out = settings.get('out')

        # option is not set or the list contains "DEFAULT" as first item
        # if the list is empty, we shouldn't replace it (e.g. if this target excludes all libs)
        self.need_default = any(arr is None or (arr and arr[0] == 'DEFAULT') for arr in [self.files, self.flags, self.libs])\
                            or self.compiler is None or self.out is None or self.asm64bit is None or self.default_asan is None
        # custom default target may still have some fields not set, so we will have to get them from a higher-level config (workspace root or package-provided)

    def __str__(self):
        return f'Target("{self.name}", compiler="{self.compiler}", flags={self.flags}, files={self.files}, libs={self.libs}, asm64bit={self.asm64bit}, default_asan={self.default_asan}, out="{self.out}")'

    def replace_macros_add_missing(self, problem, default_target):
        def modify(x):
            return x.replace('TASKNAME', problem)

        def modify_list(lst, default):
            if lst is None:
                return default
            if len(lst) == 0:
                return lst
            if lst[0] == 'DEFAULT':
                return [modify(e) for e in default + lst[1:]]
            return [modify(e) for e in lst]

        self.compiler = self.compiler or default_target.compiler
        self.files = modify_list(self.files, default_target.files)
        self.flags = modify_list(self.flags, default_target.flags)
        self.libs = modify_list(self.libs, default_target.libs)
        self.out = modify(self.out) if self.out is not None else default_target.out  # "or" doesn't work
        self.asm64bit = self.asm64bit if self.asm64bit is not None else default_target.asm64bit
        self.default_asan = self.default_asan if self.default_asan is not None else default_target.default_asan


def check_version(cfg_file, cfg, new_version, is_global=False):
    if cfg.get('__version__', new_version) == new_version:
        return

    old_version = cfg['__version__']
    click.echo(click.style(str(cfg_file.absolute()), fg='blue', bold=True) +
               click.style(' is outdated. You can run "kks init --config=update" if you want to update the default target manually (see README on Github)', fg='yellow'))
    cfg_file.write_text(re.sub(rf'^(__version__: +){old_version}', rf'\g<1>{new_version}', cfg_file.read_text(), 1, re.M))


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

    local_target = get_target(local_cfg, name)
    if local_target is not None:
        default = package_default
        if local_target.need_default:
            default = get_target(local_cfg, 'default') or get_target(root_cfg, 'default') or package_default
            if default.need_default:  # custom default target may have some missing fields
                default.replace_macros_add_missing(problem, package_default)
        local_target.replace_macros_add_missing(problem, default)
        return local_target

    root_target = get_target(root_cfg, name)
    if root_target is not None:
        default = package_default
        if root_target.need_default:
            # it makes no sense to look for default in CWD if the target is in workspace root
            default = get_target(root_cfg, 'default') or package_default
            # TODO optimize? if root_target is "default", then default == root_target and the next condition is always true
            if default.need_default:
                default.replace_macros_add_missing(problem, package_default)
        root_target.replace_macros_add_missing(problem, default)
        return root_target

    if name == 'default':
        return package_default

    package_target = get_target(package_cfg, name)
    if package_target is None:
        # not found
        return None

    package_target.replace_macros_add_missing(problem, package_default)
    return package_target
