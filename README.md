# KoKoS

Утилита для удобного решения задач курса АКОС.

Все предложения (даже самые глупые и бесполезные) принимаются в тг: [@darkkeks](https://t.me/darkkeks)

Inspired by [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn) and [petuhovskiy/acos](https://github.com/petuhovskiy/acos).

## Installation

```shell script
git clone git@github.com:darkkeks/kks.git
cd kks
pip install .
```

## Usage

### TLDR

```shell script

# Create .kks-workspace in current directory to mark kks workspace root
$ kks init

# Parse tasks from ejudge and create directories with template solutions
$ kks auth
$ kks sync

# Build and run task in current directory
$ cd sm01/1/
$ kks run
$ kks run -- arg_1 arg_2
$ kks run < input.txt > output.txt

# Format solution using clang-format
$ kks lint

# Generate tests/001.in - tests/100.in using gen.py; generate 001.out - 100.out using solve.py
$ kks gen -t 1 100 
$ kks gen -g other_gen.py -s other_solve.py -t 1 100

# Only generate *.out files (don't overwrite *.in)
# Useful if you entered tests by hand, but want to generate correct output
$ kks gen -t 1 100 -o

# Run all tests
$ kks test
```

## Todo
- build
- template
- activate / deactivate
- test
- sync
- status
- standings
- walgrind
- configure compiler
