# KoKoS

Утилита для удобного решения задач курса АКОС.

Если есть вопросы по использованию &mdash; скорее всего это значит, что ответ на эти вопросы должен быть в README.
Обязательно напишите об этом мне: [@darkkeks](https://t.me/darkkeks).
Также принимаю любые предложения и запросы фич.

Inspired by
- [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn)
- [petuhovskiy/acos](https://github.com/petuhovskiy/acos)
- [BigRedEye/cacos](https://github.com/BigRedEye/cacos)

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

Для использования не обязательна авторизация в ejudge.
Сборка, линтер, тестирование и генерация тестов будет работать без авторизации.

Авторизация используется, чтобы выкачать список задач либо парсить статус из ejudge.

Также, у `kks auth` есть флаг `--no-store-password`, который сохранит локально только логин и id контеста, но не пароль.
Пароль будет запрашиваться каждый раз, когда сессия протухает.

Без этого флага, пароль хранится в **plaintext** в файле `~/.kks/config.ini`.

### Демо

<!--suppress HtmlDeprecatedAttribute -->
<p align="center">
    <a href="https://asciinema.org/a/gurNCntp5t6ocRp2dW8vvWO7v" target="_blank">
        <!--suppress HtmlRequiredAltAttribute -->
        <img src="https://asciinema.org/a/gurNCntp5t6ocRp2dW8vvWO7v.svg" />
    </a>
</p>

### TLDR

Почти у всех команд есть адекватный `--help`, там бывают полезные аргументы, не описанные ниже.

```shell script
# Create .kks-workspace in current directory to mark kks workspace root
kks init

# Auth in ejudge
kks auth
# Dont store password in plaintext
kks auth --no-store-password

# Parse tasks from ejudge and create directories with template solutions
kks sync
# Set max line width for statements (delault 100)
MDWIDTH=70 kks sync
# Sync tasks and (latest) submissions
kks sync --code

# Show tasks status and user standings
kks status
kks status sm01 sm02-3
kks top

# Build and run solution in current directory
cd sm01/1/
kks run
kks run --sample
kks run --test 10
kks run < input.txt

# Format solution using clang-format
kks lint

# Generate tests/001.in - tests/100.in using gen.py
# Generate tests/001.out - tests/100.out using solve.py
kks gen --range 1 100
# Generate test tests/123.{in,out}
kks gen --test 123
# Only generate *.out files (don't overwrite *.in)
# Useful if you entered tests manually and want to generate correct output
kks gen --range 1 10 --output-only
# Generate tests [1; 50] using gen.sh and other_solve.py, overwriting existing tests
kks gen --generator gen.sh --solution other_solve.py --range 1 50 --force

# Test solution
kks test
# Dont stop on error
kks test --continue
# Run solution on sample
kks test --sample
# Run solution on tests [1, 10]
kks test --range 1 10
kks test --test 15 -test 16

# Submit a solution
cd sm01/1; kks submit
kks submit -p sm02-3 ./code/main.c

# Hide contest directory (move to .kks-contests)
kks hide sm01
kks hide --all
kks unhide sm03 kr01
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
        - [x] sort/filter
- sync
    - [ ] templates
    - [x] reload samples for contest/task
- activate / deactivate tasks ?
    - [x] hide whole contests
