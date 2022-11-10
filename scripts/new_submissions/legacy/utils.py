import importlib.util
import sys
from pathlib import Path


def load_module(path, relpath, name):
    module_path = Path(path).resolve().parent.joinpath(relpath).absolute()
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
