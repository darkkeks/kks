import shlex
from pathlib import Path

import yaml

from kks.util.common import find_workspace, find_problem_rootdir


target_file = 'targets.yaml'


class Target:
    all_sources = ['*.c', '*.S', '*.s']

    def __init__(self, name, settings, problem='sm00-0'):
        def modify(x):
            return x.replace('TASKNAME', problem)
        def modify_list(lst):
            return [modify(e) for e in lst]

        self.name = name
        self.files = modify_list(settings.get('files', Target.all_sources))
        self.flags = modify_list(settings.get('flags', []))
        self.libs = modify_list(settings.get('libs', []))
        self.asm64bit = bool(int(settings.get('asm64bit', 0)))
        self.out = modify(settings.get('out', ''))

    def __repr__(self):
        return f'Target("{self.name}", ...)'


default_target = Target('default', {})


def find_target(name):
    configs = []
    cwd = Path.cwd()
    cfg = cwd / target_file
    if cfg.is_file():
        configs.append(cfg)

    workspace = find_workspace()
    if workspace is not None and workspace != cwd:
        cfg = workspace / target_file  # default config
        if cfg.is_file():
            configs.append(cfg)
    
    rootdir = find_problem_rootdir()
    problem = '{}-{}'.format(*rootdir.parts[-2:]) if rootdir is not None else 'sm00-0'

    for config in configs:
        target = get_target(config, name, problem)
        if target is not None:
            return target

    if name == 'default':
        return default_target
    return None


def get_target(config_file, target_name, problem):
    found = False
    settings = {}
    with config_file.open('r') as f:
        config = yaml.safe_load(f)
    # TODO check version
    if target_name in config:
        return Target(target_name, config[target_name], problem)
    return None
