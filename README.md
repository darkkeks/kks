# KoKoS

Утилита для удобного решения задач курса АКОС.

Если есть вопросы по использованию &mdash; скорее всего это значит, что ответ на эти вопросы должен быть в README. Обязательно напишите об этом мне: [@darkkeks](https://t.me/darkkeks). Также принимаю любые предложения и запросы фич.

Inspired by [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn) and [petuhovskiy/acos](https://github.com/petuhovskiy/acos).

## Installation

### Из PyPi

```shell script
pip3 install kokos 
# or to update
pip3 install --upgrade kokos 
```

Возможно вы увидите варнинг вида

```
WARNING: The script kks is installed in '/home/darkkeks/.local/bin' which is not on PATH.
Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
```

Это значит, что скрипт не добавлен в PATH. Чтобы пользоваться им без указания пути, стоит добавить его в PATH, например в `.bashrc` вот так:
```
PATH="/home/darkkeks/.local/bin":$PATH
```

### Из исходников

```shell script
git clone https://github.com/DarkKeks/kks.git
cd kks
pip3 install .
```

## Usage

### Про пароль

Для использования не обязательна авторизация в ejudge. Сборка, линтер, тестирование и генерация тестов будет работать без авторизации.

Авторизация используется, чтобы выкачать список задач либо парсить статус из ejudge.

Также, у `kks auth` есть флаг `--no-store-password`, который сохранит локально только логин и id контеста, но не пароль. Пароль будет запрашиваться каждый раз, когда сессия протухает.

Без этого флага, пароль хранится в **plaintext** в файле `~/.kks/config.ini`.

### Демо

<!--suppress HtmlDeprecatedAttribute -->
<p align="center">
    <a href="https://asciinema.org/a/E2i72oAIMIG3mcRxEdds4Teth" target="_blank">
        <!--suppress HtmlRequiredAltAttribute -->
        <img src="https://asciinema.org/a/E2i72oAIMIG3mcRxEdds4Teth.svg" />
    </a>
</p>

### TLDR

Почти у всех команд есть адекватный `--help`, там бывают полезные аргументы, не описанные ниже.

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
- run
    - [ ] run lint on every build
    - [x] run with test as input
    - [ ] valgrind
- test
    - [x] only sample test with arg (-s, for example) and print output
    - [ ] test solve.py
    - [x] .ans/.dat ?
- gen
    - [ ] find gen.sh automatically
    - [ ] support .cpp and .c generator/solution
- build
    - [ ] configure compiler
    - [ ] support multiple files
    - [ ] support asm
- lint
    - [x] show lint diff
    - [ ] dry run ?
- ejudge
    - [x] top
        - [ ] max score
        - [ ] optimistic scoreboard
        - [ ] sort/filter
- sync
    - [ ] templates
    - [ ] reload samples for contest/task
- activate / deactivate tasks ?
