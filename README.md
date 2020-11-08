# KoKoS

Утилита для удобного решения задач курса АКОС.

Любые предложение или запросы фич принимаются в телеграм: [@darkkeks](https://t.me/darkkeks)

Inspired by [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn) and [petuhovskiy/acos](https://github.com/petuhovskiy/acos).

## Installation

```shell script
git clone git@github.com:darkkeks/kks.git
cd kks
pip install .
```

## Usage

Почти у всех команд есть адекватный `--help`, там бывают полезные аргументы, не описанные ниже.

### TLDR

```shell script
# Create .kks-workspace in current directory to mark kks workspace root
kks init

# Parse tasks from ejudge and create directories with template solutions
kks auth
kks sync

# Build and run solution in current directory
cd sm01/1/
kks run
kks run -- arg_1 arg_2
kks run < input.txt > output.txt

# Format solution using clang-format
kks lint

# Generate tests/001.in - tests/100.in using gen.py; generate 001.out - 100.out using solve.py
kks gen -r 1 100
# Generate test 123.{in,out}
kks gen -t 123
# Only generate *.out files (don't overwrite *.in)
# Useful if you entered tests manually and want to generate correct output
kks gen -r 1 10 -o
# Generate tests [1; 50] using other_gen.py and other_solve.py, overwriting existing tests
kks gen -g other_gen.py -s other_solve.py -r 1 50 -f

# Run all tests
kks test
```

## Todo
- run lint on every build
- run with test as input
- only sample test with arg (-s, for example) and print output
- test solve.py
- show lint diff
- build
- template
- activate / deactivate tasks
- standings
- valgrind
- configure compiler
- support asm
