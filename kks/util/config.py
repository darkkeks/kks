from pathlib import Path
from pkg_resources import resource_stream

import click
import yaml

from kks.util.common import find_workspace, find_problem_rootdir


target_file = 'targets.yaml'


class Target:
    def __init__(self, name, settings):
        self.name = name
        self.files = settings.get('files')
        self.flags = settings.get('flags')
        self.libs = settings.get('libs')
        self.asm64bit = settings.get('asm64bit')
        self.out = settings.get('out')

        # option is not set or the list contains "DEFAULT" as first item
        # if the list is empty, we shouldn't replace it (e.g. if this target excludes all libs)
        self.need_default = any(arr is None or (arr and arr[0] == 'DEFAULT') for arr in [self.files, self.flags, self.libs])\
                            or self.out is None or self.asm64bit is None
        # custom default target may still have some fields not set, so we will have to get them from a higher-level config (workspace root or package-provided)

    def __str__(self):
        return f'Target("{self.name}", files={self.files}, flags={self.flags}, libs={self.libs}, asm64bit={self.asm64bit}, out="{self.out}")'

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

        self.files = modify_list(self.files, default_target.files)
        self.flags = modify_list(self.flags, default_target.flags)
        self.libs = modify_list(self.libs, default_target.libs)
        self.out = modify(self.out) if self.out is not None else default_target.out
        self.asm64bit = self.asm64bit if self.asm64bit is not None else default_target.asm64bit


# package_default should have all fields set
package_default = Target('default', yaml.safe_load(resource_stream('kks', f'data/{target_file}'))['default'])


def find_target(name):
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

    cwd = Path.cwd()
    workspace = find_workspace()
    rootdir = find_problem_rootdir()
    problem = '{}-{}'.format(*rootdir.parts[-2:]) if rootdir is not None else 'sm00-0'

    if workspace is not None:
        root_file = workspace / target_file  # we load root config even if we won't need it
        root_cfg = load_config(root_file) if root_file.is_file() else None
        # TODO check root_cfg
    else:
        root_cfg = None

    if workspace is None or cwd != workspace:
        local_file = cwd / target_file
        local_cfg = load_config(local_file) if local_file.is_file() else None
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
            if default.need_default:
                default.replace_macros_add_missing(problem, package_default)
        root_target.replace_macros_add_missing(problem, default)
        return root_target

    # not found
    if name == 'default':
        return package_default
    return None
