import importlib.util
import sys
from functools import wraps


if sys.version_info.major < 3 or sys.version_info.minor < 6:
    raise RuntimeError('Python 3.6+ is required')


__all__ = ['subprocess']


def _module_copy(name):
    # NOTE submodules are shared with the original module
    spec = importlib.util.find_spec(name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _subprocess():
    if sys.version_info.minor >= 7:
        import subprocess
        return subprocess
    # don't modify original module
    subprocess = _module_copy('subprocess')
    run = subprocess.run

    @wraps(run)
    def wrapper(*args, **kwargs):
        if kwargs.pop('capture_output', False):
            # backport from 3.7+
            if kwargs.get('stdout') is not None or kwargs.get('stderr') is not None:
                raise ValueError('stdout and stderr arguments may not be used '
                                 'with capture_output.')
            kwargs['stdout'] = subprocess.PIPE
            kwargs['stderr'] = subprocess.PIPE
        return run(*args, **kwargs)

    subprocess.run = wrapper
    return subprocess


subprocess = _subprocess()
