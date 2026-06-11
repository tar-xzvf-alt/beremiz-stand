# Учебный стенд Beremiz на Linux-контроллере

Этот репозиторий хранит артефакты изучения Beremiz: проект PLC, симулятор внешнего устройства, скрипты, сетевые дампы и заметки по выполненным шагам.

README ведется как журнал: новые разделы добавляются только после успешного выполнения соответствующего шага.

## Цель

Построить небольшой стенд, где Beremiz-проект запускается на одноплатнике Linux как главный PLC-контроллер, обменивается с внешним устройством по Modbus TCP, а ПК разработчика используется для разработки, управления и мониторинга.

## Выбранная Архитектура

```text
ПК разработчика
  Beremiz IDE
  Modbus TCP simulator
  Wireshark / tcpdump
        |
        | Ethernet
        v
Starfive VisionFive 2
  Linux
  Beremiz runtime / PLC-программа
        |
        | Modbus TCP
        v
Внешнее устройство первого этапа
  Modbus TCP simulator на ПК
```

## Принятые Решения

- Главный контроллер: `Starfive VisionFive 2`.
- Первый внешний модуль: `Modbus TCP simulator`, чтобы начать без дополнительного железа и видеть обмен с ПК.
- `rt-supervisor` пока не входит в MVP; он может пригодиться позже для измерения задержек, watchdog/restart-сценариев и экспериментов с изоляцией runtime.
- Все учебные артефакты ведутся отдельно от текущих проектов `rt-supervisor` и `rt-tester`.

## Структура Репозитория

```text
beremiz-stand/
  README.md
  beremiz-project/     # проект Beremiz / PLC-логика
  modbus-simulator/    # симулятор внешнего Modbus TCP устройства
  scripts/             # вспомогательные команды и проверки
  captures/            # tcpdump/Wireshark дампы обмена
  notes/               # рабочие заметки
```

## Журнал Шагов

### Шаг 0. Создание Репозитория Стенда

Дата: 2026-06-11

Цель: создать отдельное место для всех материалов учебного стенда Beremiz.

Выполнено:

- Создан каталог `/home/taranev/work_repos/beremiz-stand/`.
- Инициализирован отдельный git-репозиторий.
- Создана базовая структура каталогов для проекта Beremiz, симулятора, скриптов, дампов и заметок.
- Зафиксирована начальная архитектура стенда.

Проверка успеха:

- Репозиторий существует отдельно от `/home/taranev/work_repos/rt/`.
- В репозитории есть этот `README.md`.
- Выбранные компоненты стенда явно описаны.

Следующий шаг:

- Шаг 1: инвентаризация ПК и `Starfive VisionFive 2` перед установкой/запуском Beremiz.

### Шаг 1. Инвентаризация ПК И Starfive VisionFive 2

Дата: 2026-06-11

Цель: проверить исходное состояние ПК разработчика, доступность платы и базовые инструменты перед установкой/запуском Beremiz.

ПК разработчика:

| Параметр | Значение |
| --- | --- |
| Hostname | `taranev` |
| ОС | `ALT Workstation K 11.4 (Nemorosa)` |
| Ядро | `Linux 6.12.85-6.12-alt1` |
| Архитектура | `x86_64` |
| Проводной интерфейс стенда | `enp2s0`, `10.42.0.1/24` |
| Wi-Fi | `wlp0s20f3`, `192.168.0.129/24` |
| Python | `3.10.20` |
| GCC | `15.2.1` |
| Make | `4.4` |
| Git | `2.50.1` |
| CMake | не установлен |
| tcpdump | `4.99.5` |
| Wireshark | `4.6.6` |
| `pymodbus` | не установлен |
| `wxPython` / модуль `wx` | не установлен |
| Пакетный менеджер | `apt` для RPM/ALT |

Starfive VisionFive 2:

| Параметр | Значение |
| --- | --- |
| Доступ | `ssh root@10.42.0.211` |
| Hostname | transient `localhost`, static hostname не задан |
| ОС | `ALT Regular` |
| Ядро | `Linux 6.18.18-rt-alt1.port.rv64`, `PREEMPT_RT` |
| Архитектура | `riscv64` |
| Интерфейс стенда | `end1`, `10.42.0.211/24` |
| Второй Ethernet | `end0`, down |
| Python | `3.13.13` |
| GCC | `15.2.1` |
| Make | `4.4` |
| CMake | `4.2.6` |
| Git | `2.50.1` |
| Пакетный менеджер | `apt` для RPM/ALT |

Проверка сети:

| Направление | Команда | Результат |
| --- | --- | --- |
| ПК -> VisionFive 2 | `ping -c 3 10.42.0.211` | 0% packet loss, avg RTT `0.570 ms` |
| VisionFive 2 -> ПК | `ssh root@10.42.0.211 ping -c 3 10.42.0.1` | 0% packet loss, avg RTT `0.510 ms` |

Вывод:

- SSH-доступ к плате работает без интерактивного ввода.
- Сеть стенда уже поднята: ПК `10.42.0.1/24`, VisionFive 2 `10.42.0.211/24`.
- На VisionFive 2 уже есть компилятор, `make`, `cmake` и `git`; плата готова к сборочным экспериментам.
- На ПК есть инструменты наблюдения сетевого обмена (`tcpdump`, Wireshark).
- Для следующих шагов на ПК нужно подготовить Python-зависимости для Modbus-симулятора и Beremiz GUI: как минимум `pymodbus`, позже `wxPython`/Beremiz-зависимости.
- Отсутствие локального `cmake` не блокирует Modbus-симулятор, но стоит учесть перед сборкой Beremiz или нативных компонентов на ПК.

Следующий шаг:

- Шаг 2: создать и запустить Modbus TCP simulator на ПК, затем проверить чтение/запись регистров и видимость обмена с VisionFive 2.

### Шаг 2. Modbus TCP Simulator На ПК

Дата: 2026-06-11

Цель: получить первое внешнее устройство для PLC-стенда без дополнительного железа.

Реализация:

- Создан `modbus-simulator/modbus_server.py`.
- Создан `modbus-simulator/modbus_client.py` для проверок.
- Реализация использует только стандартную библиотеку Python 3; внешний пакет `pymodbus` для этого шага не потребовался.
- Simulator слушает Modbus TCP на `0.0.0.0:1502`.
- Порт `1502` выбран вместо стандартного `502`, чтобы запускать simulator без root-прав.

Карта holding registers:

| Register | Назначение | Начальное значение |
| --- | --- | --- |
| `0` | `sensor_value`, имитация значения датчика | `123` |
| `1` | `output_command`, команда от PLC | `0` |
| `2` | `threshold`, порог для PLC-логики | `500` |

Поддержанные Modbus-функции:

- `3`: read holding registers.
- `4`: read input registers.
- `6`: write single holding register.
- `16`: write multiple holding registers.

Команда запуска:

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

Локальная проверка на ПК:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 1 77
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Результат:

```text
[123, 0, 500]
ok
[123, 77, 500]
```

Проверка с VisionFive 2:

```bash
scp -q modbus-simulator/modbus_client.py root@10.42.0.211:/tmp/beremiz_modbus_client.py
ssh root@10.42.0.211 python3 /tmp/beremiz_modbus_client.py 10.42.0.1 --port 1502 read-holding 0 3
ssh root@10.42.0.211 python3 /tmp/beremiz_modbus_client.py 10.42.0.1 --port 1502 write-single 1 88
ssh root@10.42.0.211 python3 /tmp/beremiz_modbus_client.py 10.42.0.1 --port 1502 read-holding 0 3
ssh root@10.42.0.211 rm -f /tmp/beremiz_modbus_client.py
```

Результат:

```text
[123, 77, 500]
ok
[123, 88, 500]
```

Проверка успеха:

- Simulator запускается на ПК на порту `1502`.
- Локальный клиент читает и пишет holding registers.
- VisionFive 2 подключается к simulator по адресу `10.42.0.1:1502` и успешно читает/пишет регистры.

Вывод:

- Первый внешний Modbus TCP модуль для стенда готов.
- Для следующего шага можно использовать simulator как устройство, к которому PLC-программа на VisionFive 2 будет обращаться по сети.

Следующий шаг:

- Шаг 3: установить/запустить Beremiz IDE на ПК и создать пустой проект для дальнейшей настройки Modbus TCP обмена.

### Шаг 3. Beremiz IDE И Пустой Проект

Дата: 2026-06-11

Цель: подтвердить наличие рабочей установки Beremiz на ПК и создать начальный пустой PLC-проект для стенда.

Проверенные пакеты на ПК:

| Пакет | Версия |
| --- | --- |
| `beremiz` | `1.5-alt0.1.20260530.1.noarch` |
| `matiec` | `20260503-alt1.x86_64` |
| `python3-module-wx` | `4.2.2-alt2.x86_64` |

Проверенная системная Python-среда Beremiz:

| Команда | Результат |
| --- | --- |
| `/usr/bin/python3 --version` | `Python 3.13.13` |
| `/usr/bin/python3 -c "import wx; print(wx.version())"` | `4.2.2 gtk3 (phoenix) wxWidgets 3.2.10` |

Важно:

- Команда `python3` из пользовательского окружения указывает на Python `3.10.20` и не видит модуль `wx`.
- Launcher `/bin/beremiz` явно использует `/usr/bin/python3`, поэтому для Beremiz нужно ориентироваться на системный Python.
- `/bin/beremiz` является shell-wrapper:

```sh
#!/bin/sh
[ -z "$WAYLAND_DISPLAY" ] || export GDK_BACKEND=x11
/usr/bin/python3 /usr/share/beremiz/Beremiz.py
```

Созданные артефакты:

- `scripts/create_empty_beremiz_project.py` — воспроизводимый скрипт создания пустого проекта через установленный Beremiz.
- `beremiz-project/study-plc/beremiz.xml` — корневой конфиг Beremiz-проекта.
- `beremiz-project/study-plc/plc.xml` — пустой PLCOpen-проект.
- `beremiz-project/README.md` — краткие команды для проекта.

Команда создания проекта:

```bash
/usr/bin/python3 scripts/create_empty_beremiz_project.py beremiz-project/study-plc
```

Содержимое созданного проекта:

```text
beremiz-project/study-plc/
  beremiz.xml
  plc.xml
  build/
```

`build/` создается Beremiz как рабочий каталог и исключен из git.

Проверка CLI-загрузки проекта:

```bash
/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc clean
```

Результат:

```text
Cleaning the build directory
PLC Status: Disconnected
```

Команда открытия проекта в IDE:

```bash
beremiz beremiz-project/study-plc
```

Проверка успеха:

- Beremiz установлен из системного ALT-пакета.
- `matiec` установлен и доступен как зависимость Beremiz.
- Системный `/usr/bin/python3` видит `wxPython`.
- Пустой проект создан штатным API Beremiz, а не ручным копированием XML.
- CLI Beremiz успешно загружает проект и выполняет `clean`.

Вывод:

- Базовая среда Beremiz на ПК готова.
- Есть валидный пустой проект, который можно дальше наполнять PLC-логикой и Modbus TCP конфигурацией.

Следующий шаг:

- Шаг 4: добавить минимальную PLC-логику и подготовить проект к обмену с Modbus TCP simulator.
