## KoKoS

Утилита для удобного решения задач курса АКОС.

Inspired by [DoomzD/caos-reborn](https://github.com/DoomzD/caos-reborn) and [petuhovskiy/acos](https://github.com/petuhovskiy/acos).

### Installation

```shell script
pip3 install kks
```
or 
```shell script
git clone git@github.com:darkkeks/kks.git
cd kks
pip install .
```

### Usage

- `kks auth` &mdash; авторизация
    
    Сохраняет логин/пароль/группу в `~/.kks/config.ini`, а также куки в `~/.kks/cookies.pickle`.
    
    Используется для вывода табличек из ejudge и загрузки списка задач.
    
- `kks init` &mdash; создание workspace

    На самом деле просто добавляет файл `.kks-workspace` в текущей директории.
    Этот файл используется, чтобы искать корень дерева папок.
    
- `kks sync` &mdash; Выгрузить список задач из ejudge // Пока не реализовано

    Выгружает из ejudge задачи с условиями и семплами.
    
    Получается что-то вроде такого:
    ```
    sm01/
    └── 1
        ├── statement.txt
        └── tests
            ├── 000.in
            └── 000.out
    ```
  
- `kks compile` &mdash; собрать решение(я) // Пока не реализовано

- `kks run` &mdash; запустить конкретное решение

- `kks test` &mdash; запустить тесты // Пока не реализовано

- `kks lint` &mdash; проверить решение линтером // Пока не реализовано


### Todo
- [ ] compile
- [ ] lint
- [ ] test
- [ ] sync
- [ ] walgrind
- [ ] configure compiler
