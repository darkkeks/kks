import subprocess

ARGS = [
    'gcc',
    '-g',
    '-Werror',
    '-Wall',
    '-Wextra',
    '-fsanitize=address',
    '-fsanitize=undefined',
]


def compile_c(workdir, files):
    filenames = list(map(lambda path: path.relative_to(workdir).as_posix(), files))

    command = ARGS + filenames
    p = subprocess.run(command, cwd=workdir)

    if p.returncode != 0:
        return None

    return workdir / 'a.out'


