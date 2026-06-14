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

### Шаг 4. PLC-Логика И Modbus TCP Client

Дата: 2026-06-11

Цель: добавить минимальную PLC-логику в `study-plc`, настроить Modbus TCP client к simulator и проверить сборку проекта.

Изученные источники:

- `/usr/share/beremiz/projects/modbus_test_tcp/` — штатный пример Beremiz с Modbus TCP client/server.
- `/usr/share/beremiz/modbus/modbus_base.py` — схема параметров Modbus request и правила формирования IEC locations.
- `/usr/share/beremiz/util/paths.py` — подтверждено, что путь к сторонней Modbus-библиотеке можно задавать через `MODBUS_PATH`.

Созданные/измененные артефакты:

- `scripts/configure_study_plc.py` — воспроизводимо генерирует PLC-логику и Modbus confnode-файлы проекта.
- `scripts/prepare_modbus_source.sh` — готовит локальную сборку Modbus C-библиотеки из установленного source-пакета.
- `beremiz-project/study-plc/plc.xml` — теперь содержит программу `plc_prg` на ST.
- `beremiz-project/study-plc/modbus_0@modbus/` — конфигурация Modbus TCP client и двух Modbus requests.
- `beremiz-project/README.md` — добавлены карта регистров и команды сборки.

Modbus TCP client:

| Параметр | Значение |
| --- | --- |
| Remote IP | `10.42.0.1` |
| Remote port | `1502` |
| Invocation rate | `100 ms` |
| Request delay | `0 ms` |

Modbus requests:

| Request | Function | Start address | Count | Назначение |
| --- | --- | --- | --- | --- |
| `ReadHolding_0` | `03 - Read Holding Registers` | `0` | `3` | прочитать `sensor_value`, `output_command`, `threshold` из simulator |
| `WriteOutput_1` | `06 - Write Single Register` | `1` | `1` | записать PLC-команду в holding register `1` simulator |

PLC-логика:

```iecst
ReadRequestExecute := TRUE;
WriteRequestExecute := TRUE;

sensor_value := WORD_TO_UINT(SensorRegister);
threshold := WORD_TO_UINT(ThresholdRegister);
remote_output_echo := WORD_TO_UINT(RemoteOutputRegister);

alarm := sensor_value > threshold;

IF alarm THEN
    output_command := UINT#1;
ELSE
    output_command := UINT#0;
END_IF;

OutputCommandRegister := UINT_TO_WORD(output_command);
```

Карта регистров:

| Simulator holding register | PLC variable | IEC location | Direction |
| --- | --- | --- | --- |
| `0` | `SensorRegister` / `sensor_value` | `%IW0.0.0.0` | read |
| `1` | `RemoteOutputRegister` / `remote_output_echo` | `%IW0.0.0.1` | read |
| `2` | `ThresholdRegister` / `threshold` | `%IW0.0.0.2` | read |
| `1` | `OutputCommandRegister` / `output_command` | `%QW0.0.1.1` | write |

Modbus C-зависимость:

- Нужный ALT-пакет: `beremiz-modbus-source-20170318-alt1.noarch`.
- Пакет кладет исходники в `/usr/src/beremiz-modbus`.
- Beremiz по умолчанию ищет `Modbus` рядом с `/usr/share/beremiz`, поэтому для сборки используем `MODBUS_PATH`.
- Старые исходники используют `<termio.h>`; `scripts/prepare_modbus_source.sh` копирует исходники в `.deps/Modbus`, заменяет include на `<termios.h>` только в локальной копии и собирает `libmb.a`/`libmb.so`.

Команды проверки:

```bash
/usr/bin/python3 scripts/configure_study_plc.py beremiz-project/study-plc
scripts/prepare_modbus_source.sh
MODBUS_PATH="$PWD/.deps/Modbus" /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc clean build
```

Результат сборки:

```text
Successfully built.
PLC Status: Disconnected
```

Наблюдение:

- При сборке остаются предупреждения GCC в сгенерированном `MB_0.c` про `server_nodes` размера 0.
- Проект использует только Modbus client без server nodes; предупреждения не остановили сборку и линковку.

Проверка успеха:

- Beremiz CLI загружает проект без XML schema warning.
- IEC/ST код успешно преобразуется в C.
- `LOCATED_VARIABLES.h` содержит ожидаемые Modbus locations.
- Сборка с `MODBUS_PATH=$PWD/.deps/Modbus` завершается `Successfully built`.

Вывод:

- `study-plc` готов как минимальный Beremiz-проект с Modbus TCP client-конфигурацией.
- Следующий этап должен проверить не только сборку, но и реальный запуск runtime/PLC с подключением к simulator.

Следующий шаг:

- Шаг 5: подготовить target/runtime-сценарий для запуска PLC на VisionFive 2 и проверить доступность Modbus simulator с этого runtime.

### Шаг 5. Запуск PLC Runtime На VisionFive 2

Дата: 2026-06-11

Цель: собрать `study-plc` нативно на `Starfive VisionFive 2`, запустить Beremiz local runtime на плате и подтвердить реальный Modbus TCP обмен с simulator на ПК.

Важное ограничение сети:

- VisionFive 2 подключен к ПК напрямую через Ethernet bridge и не должен полагаться на интернет-доступ.
- Git/pull с платы может зависать из-за VPN/маршрутизации на ПК.
- Для переноса стенда на плату используется прямой `scp` с ПК, а не `git clone` на плате.

Пакеты на VisionFive 2 после ручной подготовки:

| Пакет | Версия |
| --- | --- |
| `beremiz` | `1.4-alt0.1.20250821.2.noarch` |
| `matiec` | `20250821-alt1.riscv64` |
| `beremiz-modbus-source` | `20170318-alt1.noarch` |
| `python3-module-erpc` | `1.13.0-alt1.noarch` |
| `python3-module-twisted-core` | `24.11.0-alt2.noarch` |
| `python3-module-click` | `8.4.1-alt1.noarch` |

Локальный RPM:

- `beremiz-modbus-source-20170318-alt1.noarch.rpm` добавлен в репозиторий стенда как резервный артефакт.
- На плату он устанавливался командой:

```bash
scp -q beremiz-modbus-source-20170318-alt1.noarch.rpm root@10.42.0.211:/tmp/beremiz-modbus-source-20170318-alt1.noarch.rpm
ssh root@10.42.0.211 'rpm -Uvh /tmp/beremiz-modbus-source-20170318-alt1.noarch.rpm'
```

Перенос рабочей копии на плату:

```bash
scripts/sync_to_visionfive.sh
```

Скрипт архивирует текущий каталог, исключая `.git`, `.deps`, `beremiz-project/*/build` и `__pycache__`, затем распаковывает его в `/root/beremiz-stand` на VisionFive 2.

Наблюдение:

- При распаковке на плате `tar` предупреждал о timestamps "в будущем".
- Это связано с рассинхроном времени: ПК живет в дате `2026-06-11`, а VisionFive 2 во время теста показывал дату `2026-02-27`.
- На результат сборки/запуска это не повлияло.

Подготовка Modbus C-библиотеки на плате:

```bash
ssh root@10.42.0.211 'cd /root/beremiz-stand && ./scripts/prepare_modbus_source.sh'
```

Результат:

```text
Prepared Modbus library in .deps/Modbus
```

Нативная сборка PLC на VisionFive 2:

```bash
ssh root@10.42.0.211 'cd /root/beremiz-stand && rm -rf beremiz-project/study-plc/build && MODBUS_PATH="/root/beremiz-stand/.deps/Modbus" /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc build'
```

Проверенный результат:

```text
Linking :
   [CC]  plc_main.o plc_debugger.o py_ext.o config.o resource1.o MB_0.o -> study-plc.so
Successfully built.
```

Проверка архитектуры build-артефакта:

```bash
ssh root@10.42.0.211 'file /root/beremiz-stand/beremiz-project/study-plc/build/study-plc.so'
```

Результат:

```text
ELF 64-bit LSB shared object, UCB RISC-V, RVC, double-float ABI
```

Отличие Beremiz CLI на плате:

- На ПК установлен Beremiz `1.5`, где есть команда `clean`.
- На VisionFive 2 установлен Beremiz `1.4`, где CLI поддерживает только `build`, `connect`, `transfer`, `run`, `stop`.
- Поэтому на плате очистка делалась удалением `beremiz-project/study-plc/build`, а команда `clean` не использовалась.

Runtime smoke test:

На ПК запущен simulator:

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

Перед запуском PLC выставлены регистры simulator:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 0 600
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 1 0
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Начальное состояние:

```text
[600, 0, 500]
```

На VisionFive 2 запущен local runtime через Beremiz CLI:

```bash
ssh root@10.42.0.211 'cd /root/beremiz-stand && MODBUS_PATH="/root/beremiz-stand/.deps/Modbus" timeout 30s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --keep transfer run'
```

Ключевые строки runtime:

```text
Starting local runtime...
Beremiz_service:  1.4
PLC data transfered successfully.
PLC installed successfully.
PLCobject : PLC started
PLCobject : Python extensions started
Starting PLC
```

`timeout` завершил процесс с кодом `124`; это ожидаемо для кратковременного smoke test с `--keep`.

Фрагмент simulator log, подтверждающий обмен с платы:

```text
client connected: 10.42.0.211:40796
read fc=3 start=0 count=3 values=[600, 0, 500]
write fc=6 address=1 value=0
read fc=3 start=0 count=3 values=[600, 0, 500]
write fc=6 address=1 value=1
read fc=3 start=0 count=3 values=[600, 1, 500]
```

Финальная проверка регистров simulator:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Результат:

```text
[600, 1, 500]
```

Проверка успеха:

- PLC собран нативно на VisionFive 2 под `riscv64`.
- Beremiz local runtime на VisionFive 2 стартовал и принял PLC через `transfer`.
- Simulator на ПК получил Modbus TCP запросы от `10.42.0.211`.
- PLC прочитал `sensor_value=600`, `threshold=500` и записал `output_command=1` в holding register `1`.

Вывод:

- Минимальный стенд теперь работает end-to-end: ПК simulator -> VisionFive 2 Beremiz runtime -> Modbus TCP -> ПК simulator.
- Следующий этап можно посвятить нормальному запуску runtime как сервиса на плате и подключению IDE/online-monitoring с ПК.

Следующий шаг:

- Шаг 6: оформить постоянный/повторяемый запуск Beremiz runtime на VisionFive 2 и подключение Beremiz IDE с ПК для online monitoring.

### Шаг 6. Persistent Runtime На VisionFive 2

Дата: 2026-06-11

Цель: заменить временный local runtime из smoke test на управляемый `Beremiz_service.py`, который постоянно слушает ERPC на VisionFive 2 и принимает загрузку PLC с CLI.

Добавленные скрипты:

- `scripts/start_runtime_on_visionfive.sh` — запускает `Beremiz_service.py` на плате в фоне.
- `scripts/stop_runtime_on_visionfive.sh` — останавливает запущенный runtime по pidfile.
- `scripts/deploy_run_on_visionfive_runtime.sh` — загружает `study-plc` в уже запущенный runtime и запускает PLC.
- `scripts/check_runtime_status.py` — проверяет статус runtime по ERPC с ПК без чтения runtime-логов.

Выбранные параметры runtime:

| Параметр | Значение |
| --- | --- |
| Runtime host | `10.42.0.211` |
| Runtime port | `3000` |
| Runtime URI | `ERPC://10.42.0.211:3000` |
| Runtime working dir | `/root/beremiz-runtime/study-plc` |
| Исходники стенда на плате | `/root/beremiz-stand` |
| Web UI / Twisted | выключены: `-t 0 -w off` |
| wx taskbar | выключен: `-x 0` |

Команда запуска runtime:

```bash
scripts/start_runtime_on_visionfive.sh
```

Результат:

```text
Beremiz runtime started on 10.42.0.211:3000
```

Проверка загрузки и запуска PLC в persistent runtime:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 0 600
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 1 0
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
scripts/deploy_run_on_visionfive_runtime.sh
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Ключевые строки `deploy_run_on_visionfive_runtime.sh`:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
Version string: Linux 6.18.18-rt-alt1.port.rv64
PLC data transfered successfully.
PLC installed successfully.
Starting PLC
```

Состояние registers simulator:

```text
[600, 0, 500]
[600, 1, 500]
```

Проверка статуса runtime с ПК:

```bash
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

Результат после запуска PLC:

```text
PLC Status: Started
Log counts: [0, 0, 0, 3]
```

Проверка остановки и повторного старта runtime:

```bash
scripts/stop_runtime_on_visionfive.sh
scripts/start_runtime_on_visionfive.sh
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

Результат:

```text
Beremiz runtime stopped
Beremiz runtime started on 10.42.0.211:3000
PLC Status: Stopped
Log counts: [0, 0, 0, 0]
```

Ограничение online monitoring с ПК:

- ПК использует Beremiz `1.5-alt0.1.20260530.1.noarch`.
- VisionFive 2 использует Beremiz_service `1.4-alt0.1.20250821.2.noarch`.
- Команда `/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --uri ERPC://10.42.0.211:3000 connect` подключается к runtime, видит `PLC Status: Started`, но затем получает ошибку при `GetLogMessage`.
- Ошибка выглядит как несовместимость eRPC-структуры log message между версиями `1.5` и `1.4`: `struct.error: unpack_from requires a buffer ...`.
- Поэтому для автоматической проверки статуса используется `scripts/check_runtime_status.py`, который вызывает только `GetPLCstatus` и не читает runtime logs.
- Полноценный IDE online monitoring с ПК нужно проверять после выравнивания версий Beremiz на ПК и плате или после отдельного workaround для чтения логов.

Проверка успеха:

- `Beremiz_service.py` запускается как отдельный долгоживущий процесс на VisionFive 2.
- ERPC runtime доступен по `ERPC://10.42.0.211:3000`.
- PLC загружается в persistent runtime через `transfer run`, без временного local runtime.
- Simulator подтверждает реальный Modbus TCP exchange с платы: register `1` меняется на `1` при `sensor_value=600` и `threshold=500`.
- Статус runtime проверяется с ПК отдельным скриптом и показывает `PLC Status: Started`.
- Stop/start runtime повторяемы и оставляют сервис в понятном состоянии.

Вывод:

- Runtime-часть стенда стала повторяемой: исходники синхронизируются на плату, проект собирается нативно, runtime запускается отдельно, PLC загружается и запускается по ERPC.
- Главный оставшийся риск для online monitoring — несовпадение версий Beremiz `1.5` на ПК и `1.4` на VisionFive 2.

Следующий шаг:

- Шаг 7: выровнять версии Beremiz для ПК и VisionFive 2 или найти безопасный способ online monitoring без ошибки `GetLogMessage`.

### Шаг 7. Совместимость Online Monitoring Между Beremiz 1.5 И Runtime 1.4

Дата: 2026-06-14

Цель: устранить ошибку `GetLogMessage`, из-за которой Beremiz CLI/IDE `1.5` на ПК не мог стабильно мониторить `Beremiz_service.py` `1.4` на VisionFive 2.

Диагностика:

- `runtime/eRPCServer.py` на ПК и плате совпадает по `sha256`.
- `connectors/ERPC/__init__.py` на ПК и плате совпадает по `sha256`.
- Сгенерированные stubs `erpc_interface/erpc_PLCObject/{common,client,server}.py` отличаются.
- Конкретное отличие, ломавшее чтение логов: в Beremiz `1.4` поле `log_message.sec` сериализуется как `uint32`, а в Beremiz `1.5` клиент ожидает `uint64`.
- Второе отличие runtime `1.4`: `PLCObject.GetLogMessage()` может вернуть `None` для пустого сообщения, а общий `eRPCServer.py` ожидает tuple для `log_message(*res)`.

Решение:

- Добавлен runtime extension `scripts/beremiz_runtime_compat_15.py`.
- Extension загружается штатным параметром `Beremiz_service.py -e ...`; системные файлы `/usr/share/beremiz` не изменяются.
- Extension меняет только runtime-поведение для ERPC log messages:
- `common.log_message._write` на плате пишет `sec` как `uint64`, как ожидает Beremiz `1.5` на ПК.
- `PLCObject.GetLogMessage` на плате возвращает пустой tuple `("", 0, 0, 0)` вместо `None`, чтобы ERPC server не падал на пустом сообщении.
- `eRPCServer.Loop` на плате обрабатывает `ConnectionResetError` как обычное отключение клиента, чтобы `timeout`/закрытие CLI или IDE не оставляли сервис живым, но без работающего RPC thread.
- `scripts/start_runtime_on_visionfive.sh` автоматически подключает extension, если он есть в `/root/beremiz-stand/scripts/beremiz_runtime_compat_15.py`.

Также изменено:

- `scripts/sync_to_visionfive.sh` теперь исключает `beremiz-project/*/psk`, чтобы не переносить локальные Beremiz PSK/management-файлы на плату.

Команды проверки:

```bash
scripts/sync_to_visionfive.sh
scripts/stop_runtime_on_visionfive.sh
scripts/start_runtime_on_visionfive.sh
scripts/build_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
timeout 8s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --uri ERPC://10.42.0.211:3000 --keep connect
```

Ключевой результат обычного Beremiz CLI `1.5` с ПК:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
Version string: Linux 6.18.18-rt-alt1.port.rv64
DEBUG at 2026-02-27 12:01:58.996522+00:00: PLC started
DEBUG at 2026-02-27 12:01:58.997037+00:00: Python extensions started
PLC Status: Started
Debugger ready
Press Ctrl+C to quit
PLC Status: Started
```

Важно:

- Команда выше завершается через `timeout`; код `124` для такой проверки ожидаем и был обработан как успех.
- Строки `Stats[1970-01-01 00:00:00+00:00]` остаются, но не мешают подключению и monitoring loop.
- `Latest build does not match with connected target` при `connect` с ПК ожидаем, потому что проект на ПК не является riscv64-сборкой; deploy/run выполняется с нативной сборки на VisionFive 2.

Проверка Modbus после исправления monitoring:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Результат:

```text
[600, 1, 500]
```

Проверка успеха:

- Обычный Beremiz CLI `1.5` на ПК подключается к `Beremiz_service.py` `1.4` на VisionFive 2 без traceback `GetLogMessage`.
- `--keep connect` держит monitoring loop и повторно видит `PLC Status: Started`.
- Runtime logs читаются с ПК.
- Runtime остается доступен после принудительного завершения monitoring-клиента через `timeout`.
- PLC продолжает работать и писать `output_command=1` в Modbus simulator.
- Исправление не требует переустановки Beremiz на ПК или VisionFive 2.

Вывод:

- Online monitoring через ERPC стал практически пригоден для текущего смешанного набора версий: ПК Beremiz `1.5`, VisionFive 2 runtime `1.4`.
- Для IDE нужно запускать штатный `beremiz beremiz-project/study-plc`, указать URI `ERPC://10.42.0.211:3000` и подключаться к runtime; compatibility находится на стороне runtime.

Следующий шаг:

- Шаг 8: проверить Beremiz IDE online view вручную в GUI и зафиксировать, какие переменные удобно наблюдать/форсировать в `study-plc`.

### Шаг 8. Подготовка Beremiz IDE К Online View

Дата: 2026-06-14

Цель: сделать запуск IDE для `study-plc` удобным: проект должен открываться с уже заданным remote runtime URI, а не с `LOCAL://`.

Изменения:

- В `beremiz-project/study-plc/beremiz.xml` URI изменен с `LOCAL://` на `ERPC://10.42.0.211:3000`.
- В `scripts/configure_study_plc.py` внесено то же значение, чтобы повторная генерация проекта не возвращала `LOCAL://`.
- В `beremiz-project/README.md` добавлены команда запуска IDE и список переменных для online monitoring.

Проверка GUI-среды на ПК:

```bash
/usr/bin/python3 - <<'PY'
import wx
app = wx.App(False)
print('wx-ok')
PY
```

Результат:

```text
wx-ok
```

Проверка, что CLI берет URI из `beremiz.xml` без явного `--uri`:

```bash
timeout 8s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --keep connect
```

Ключевой результат:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
Version string: Linux 6.18.18-rt-alt1.port.rv64
PLC Status: Started
Debugger ready
Press Ctrl+C to quit
PLC Status: Started
```

Проверка запуска IDE:

```bash
timeout 12s beremiz beremiz-project/study-plc
```

Результат:

```text
beremiz-gui-started-timeout
```

Наблюдение:

- GUI стартует в текущей графической сессии (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`).
- Traceback `RuntimeError: wrapped C/C++ object of type Menu has been deleted` появился только при принудительном завершении через `timeout`, то есть при автоматическом закрытии окна, а не при обычном запуске.
- Автоматически проверить клики в IDE из CLI нельзя; фактическая ERPC monitoring-сессия проверена через Beremiz CLI с тем же URI из проекта.

Команда ручной проверки IDE:

```bash
beremiz beremiz-project/study-plc
```

Что проверять в IDE online view:

| Variable | Ожидаемое значение при registers `[600, 1, 500]` |
| --- | --- |
| `sensor_value` | `600` |
| `threshold` | `500` |
| `remote_output_echo` | `1` |
| `alarm` | `TRUE` |
| `output_command` | `1` |
| `SensorRegister` | `16#0258` |
| `ThresholdRegister` | `16#01F4` |
| `OutputCommandRegister` | `16#0001` |

Проверка Modbus-состояния после запуска PLC:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Результат:

```text
[600, 1, 500]
```

Проверка успеха:

- Проект хранит remote runtime URI `ERPC://10.42.0.211:3000`.
- Beremiz CLI подключается к runtime без `--uri`, используя `beremiz.xml`.
- Две последовательные проверки `timeout 5s ... --keep connect` не ломают runtime; после них `scripts/check_runtime_status.py` показывает `PLC Status: Started`.
- IDE запускается с проектом в доступной GUI-сессии.
- Переменные для ручного online monitoring перечислены и привязаны к текущей Modbus-карте.

Вывод:

- Стенд готов к ручной проверке Beremiz IDE online view: runtime уже удаленный, compatibility extension работает на плате, URI хранится в проекте.

Следующий шаг:

- Шаг 9: добавить простую процедуру демонстрации — менять `sensor_value` в simulator ниже/выше `threshold` и наблюдать переключение `alarm`/`output_command` в IDE и Modbus register `1`.

### Шаг 9. Демонстрация Переключения Alarm

Дата: 2026-06-14

Цель: получить короткий повторяемый сценарий, который показывает работу PLC-логики: при `sensor_value <= threshold` команда выключена, при `sensor_value > threshold` команда включена.

Добавлен скрипт:

- `scripts/demo_alarm_toggle.py`

Что делает скрипт:

- Подключается к Modbus simulator на `127.0.0.1:1502`.
- Ставит `threshold=500` в holding register `2`.
- Перед каждым кейсом намеренно записывает register `1` в неправильное значение.
- Меняет `sensor_value` в holding register `0`.
- Ждет, пока PLC на VisionFive 2 прочитает registers и перезапишет holding register `1` правильным `output_command`.

Команды проверки:

```bash
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
/usr/bin/python3 scripts/demo_alarm_toggle.py
```

Результат:

```text
LOW: sensor=400, threshold=500, forced_output=1, initial=[400, 1, 500], final=[400, 0, 500]
HIGH: sensor=600, threshold=500, forced_output=0, initial=[600, 0, 500], final=[600, 1, 500]
LOW-AGAIN: sensor=250, threshold=500, forced_output=1, initial=[250, 1, 500], final=[250, 0, 500]
demo passed
```

Проверка runtime после demo:

```bash
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

Результат:

```text
PLC Status: Started
Log counts: [0, 0, 0, 3]
```

Финальное состояние Modbus registers:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Результат:

```text
[250, 0, 500]
```

Проверка online monitoring после demo:

```bash
timeout 5s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --keep connect
```

Ключевой результат:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
PLC Status: Started
Debugger ready
Press Ctrl+C to quit
PLC Status: Started
```

Как наблюдать это в IDE:

```bash
beremiz beremiz-project/study-plc
```

В проекте уже сохранен URI `ERPC://10.42.0.211:3000`, поэтому IDE должна подключаться к runtime на VisionFive 2, а не запускать локальный runtime.

Переменные для наблюдения:

| Variable | LOW после demo | HIGH во время demo | LOW-AGAIN после demo |
| --- | --- | --- | --- |
| `sensor_value` | `400` | `600` | `250` |
| `threshold` | `500` | `500` | `500` |
| `remote_output_echo` | `0` | `1` | `0` |
| `alarm` | `FALSE` | `TRUE` | `FALSE` |
| `output_command` | `0` | `1` | `0` |
| `SensorRegister` | `16#0190` | `16#0258` | `16#00FA` |
| `ThresholdRegister` | `16#01F4` | `16#01F4` | `16#01F4` |
| `OutputCommandRegister` | `16#0000` | `16#0001` | `16#0000` |

Проверка успеха:

- PLC на VisionFive 2 реагирует на изменение Modbus register `0`.
- Register `1` меняется не самим demo-скриптом в правильную сторону, а PLC-программой после чтения `sensor_value` и `threshold`.
- Runtime остается `Started` после demo.
- Online monitoring через CLI остается рабочим.

Вывод:

- Теперь стенд имеет понятный демонстрационный сценарий: можно запускать demo и одновременно смотреть в IDE, как меняются `sensor_value`, `alarm` и `output_command`.

Следующий шаг:

- Шаг 10: добавить tcpdump/Wireshark capture этого сценария, чтобы связать переменные PLC с реальными Modbus TCP пакетами.
