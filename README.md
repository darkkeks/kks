# KoKoS

Утилита для удобного решения задач курса АКОС.

Фидбек можно писать в issue, либо в телеграм [@darkkeks](https://t.me/darkkeks).

Inspired by
- [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn)
- [petuhovskiy/acos](https://github.com/petuhovskiy/acos)
- [BigRedEye/cacos](https://github.com/BigRedEye/cacos)

## Installation

### Из PyPi

```shell
pip3 install kokos
```

<details>
  <summary>Возможные проблемы</summary>

  - Скрипт не добавлен в `PATH`. При установке будет варнинг такого вида:

    ```
    WARNING: The script kks is installed in '/home/darkkeks/.local/bin' which is not on PATH.
    Consider adding this directory to PATH or, if you prefer to suppress this warning, use --no-warn-script-location.
    ```

    Чтобы добавить его в `PATH`, можно дописать подобную строку в `.bashrc`/`.zshrc`:
    ```shell
    PATH="/home/darkkeks/.local/bin":"$PATH"
    ```
</details>

### Обновление

```shell
kks update
```

### Из исходников

```shell script
git clone https://github.com/DarkKeks/kks.git
cd kks
pip3 install .
```

## Usage

<details>
  <summary>Про пароль</summary>

  Для использования не обязательна авторизация в ejudge.
  Сборка, линтер, тестирование и генерация тестов будет работать без авторизации.

  Также, у `kks auth` есть флаг `--no-store-password`, который сохранит локально только логин и id контеста, но не пароль.
  Пароль будет запрашиваться каждый раз, когда сессия протухает.

  Без этого флага, пароль хранится в **plaintext** в файле `~/.kks/config.ini`.
</details>

<details>
  <summary><b>Глобальные опции и параметры</b></summary>

  Настраиваемые параметры (данные для авторизации и глобальные опции) хранятся в файле `~/.kks/config.ini`

  #### Auth
  Данные для авторизации в Ejudge

  Доступные опции - `login`, `contest`, `password` (опционально)

  #### Options
  Глобальные опции, можно переопределять через переменные окружения

  Опции:
   - `mdwidth` (по умолчанию `100`) - максимальная ширина текста в условиях при конвертации в Markdown
   - `max-kr` - считать максимальные баллы для тестирующихся задач из КР (`kks top --max`). Результаты могут значительно отличаться от реальных баллов.
   - `deadline-warning-days` - за сколько дней до дедлайна выделять контест в выводе `kks deadlines` и `kks status --todo` (по умолчанию - 1 день)
   - `sort-todo-by-deadline` (по умолчанию `True`) - включить сортировку по дедлайнам в `kks status --todo`
   - `global-opt-out` - отказаться от отправки статистики для глобального рейтинга
   - `save-html-statements`, `save-md-statements` (по умолчанию оба значения `true`) - выбор формата сохранения условий при синхронизации
   - `save-attachments` (по умолчанию `true`) - сохранять приложенные к условиям файлы

  Имена переменных окружения, если они используются, должны быть в upper-case. Например, для переопределения опции `save-html-statements` используется переменная окружения `SAVE_HTML_STATEMENTS`

</details>

[comment]: <> (### Демо)

[comment]: <> (<!--suppress HtmlDeprecatedAttribute -->)

[comment]: <> (<p align="center">)

[comment]: <> (    <a href="https://asciinema.org/a/gurNCntp5t6ocRp2dW8vvWO7v" target="_blank">)

[comment]: <> (        <!--suppress HtmlRequiredAltAttribute -->)

[comment]: <> (        <img src="https://asciinema.org/a/gurNCntp5t6ocRp2dW8vvWO7v.svg" />)

[comment]: <> (    </a>)

[comment]: <> (</p>)

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
# Set max line width for statements (default 100)
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

# build without stdlib
cd sm10/2
kks run -T nostd
# build without stdlib (force 32-bit mode)
kks run -T nostd32

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

# Submit a solution (problem and solution are auto-detected)
# There will be a confirmation before every submit, to avoid accidental submits
kks submit
# Manually specify problem and source file
kks submit -p sm02-3 ./code/main.c

# Hide contest directory (move to .kks-contests)
kks hide sm01
kks hide --all
kks unhide sm03 kr01
```

## Файлы конфигурации

Используются, если нужно изменить флаги компилятора по умолчанию / добавить дополнительные варианты сборки (например, для дебага).

Если в корневой директории воркспейса существует файл `targets.yaml`, то все таргеты из него доступны в любой поддиректории (являются глобальными).
Если `targets.yaml` существует в рабочей директории, то описания таргетов из него являются более приоритетными по сравнению с глобальными.

**Для решений, написанных на C++, таргеты влияют только на список файлов (параметр `files`)**

```shell script
# Создать файл в рабочей директории
kks init --config

# Создать глобальный конфиг для существующего воркспейса
kks init --config=global

# Собрать и запустить решение с таргетом "debug"
kks run -T debug
```

При запуске `kks run` или `kks test` можно получить предупреждение следующего вида:

```
/path/to/targets.yaml is outdated. You can run "kks init --config=update" if you want to update the default target manually
```

Это значит, что параметры сборки по умолчанию (без использования файлов конфигурации) были обновлены.
В таком случае стоит запустить `kks init --config=update` в директории с указанным файлом и вручную добавить необходимые изменения.
Если этого не cделать, могут появиться проблемы при компиляции решений для (некоторых) новых задач.
