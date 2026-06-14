# Учебный Стенд Beremiz На Linux-Контроллере

Репозиторий содержит минимальный рабочий стенд для изучения Beremiz: PLC-программа запускается на `Starfive VisionFive 2`, а внешнее устройство моделируется на ПК как Modbus TCP server.

Пошаговый запуск вынесен в [GUIDE.md](GUIDE.md).

## Суть Стенда

Стенд показывает полный цикл работы Linux PLC:

- разработка проекта Beremiz на ПК;
- нативная сборка PLC на `riscv64` плате VisionFive 2;
- запуск `Beremiz_service.py` как persistent runtime на плате;
- обмен PLC с внешним устройством по Modbus TCP;
- online monitoring с ПК через ERPC;
- демонстрация переключения `alarm` и `output_command` при изменении входного значения датчика.

Архитектура:

```text
ПК разработчика, 10.42.0.1
  Beremiz IDE / CLI 1.5
  Modbus TCP simulator, port 1502
  scripts и документация
        |
        | Ethernet
        v
Starfive VisionFive 2, 10.42.0.211
  ALT Regular riscv64
  PREEMPT_RT kernel
  Beremiz runtime 1.4, ERPC port 3000
  study-plc.so
        |
        | Modbus TCP client -> 10.42.0.1:1502
        v
Modbus holding registers simulator
```

## Что Реализовано

Основные артефакты:

| Path | Назначение |
| --- | --- |
| `beremiz-project/study-plc/` | Beremiz PLC project |
| `modbus-simulator/modbus_server.py` | Modbus TCP simulator на стандартной библиотеке Python |
| `modbus-simulator/modbus_client.py` | Утилита чтения/записи Modbus registers |
| `scripts/sync_to_visionfive.sh` | Передача репозитория на VisionFive 2 через `scp` |
| `scripts/build_on_visionfive.sh` | Нативная сборка PLC на VisionFive 2 |
| `scripts/start_runtime_on_visionfive.sh` | Запуск persistent Beremiz runtime на плате |
| `scripts/deploy_run_on_visionfive_runtime.sh` | Transfer/run PLC в уже запущенный runtime |
| `scripts/check_runtime_status.py` | Проверка ERPC runtime без чтения runtime logs |
| `scripts/demo_alarm_toggle.py` | Демонстрация переключения alarm/output |
| `scripts/beremiz_runtime_compat_15.py` | Runtime compatibility layer для Beremiz 1.5 client -> 1.4 runtime |
| `beremiz-modbus-source-20170318-alt1.noarch.rpm` | Offline RPM с Modbus C sources |

## PLC-Логика

Modbus simulator хранит три holding registers:

| Register | Назначение |
| --- | --- |
| `0` | `sensor_value` |
| `1` | `output_command` |
| `2` | `threshold` |

PLC каждые `100 ms` читает registers `0..2`, вычисляет alarm и пишет результат в register `1`:

```iecst
alarm := sensor_value > threshold;

IF alarm THEN
    output_command := UINT#1;
ELSE
    output_command := UINT#0;
END_IF;
```

Проверенный сценарий:

```text
sensor=400, threshold=500 -> alarm=FALSE -> output_command=0
sensor=600, threshold=500 -> alarm=TRUE  -> output_command=1
sensor=250, threshold=500 -> alarm=FALSE -> output_command=0
```

## Как Стенд Воссоздан

Стенд был собран по шагам:

1. Создан отдельный репозиторий `beremiz-stand`, чтобы не смешивать материалы с другими RT-проектами.
2. Проверена сеть ПК <-> VisionFive 2: ПК `10.42.0.1`, плата `10.42.0.211`.
3. Написан Modbus TCP simulator без внешних Python-зависимостей.
4. Создан Beremiz project `study-plc` через штатный API `ProjectController.NewProject`.
5. Добавлены ST-логика PLC и Modbus TCP client configuration.
6. Подготовлен локальный Modbus C source tree из пакета `beremiz-modbus-source`.
7. Проект собран на ПК для первичной проверки и на VisionFive 2 для настоящего `riscv64` runtime artifact.
8. Запущен `Beremiz_service.py` на VisionFive 2 как persistent ERPC runtime.
9. PLC загружен в runtime через `transfer run`.
10. Online monitoring с ПК восстановлен через runtime compatibility extension.
11. Добавлен demo-сценарий, который доказывает, что register `1` меняет именно PLC.

Практические команды запуска описаны в [GUIDE.md](GUIDE.md).

## Что Пришлось Поменять, Чтобы Заработало

### Передача На Плату Без Git

VisionFive 2 подключен напрямую к ПК через Ethernet. `git clone`/`git pull` на плате нежелателен и может зависать из-за сети/VPN. Поэтому сделан `scripts/sync_to_visionfive.sh`, который передает рабочую копию через `scp`.

### Нативная Сборка На VisionFive 2

PLC shared object должен быть `riscv64`, поэтому финальная сборка выполняется на плате:

```bash
scripts/build_on_visionfive.sh
```

### Modbus C Sources

Beremiz ожидает Modbus C sources через `MODBUS_PATH`. Скрипт `scripts/prepare_modbus_source.sh` копирует `/usr/src/beremiz-modbus` в `.deps/Modbus`, применяет локальную замену `termio.h -> termios.h` и собирает библиотеку.

### Persistent Runtime Вместо Local Runtime

Первичный smoke test запускал local runtime через Beremiz CLI. Для стенда нужен отдельный runtime на плате, поэтому добавлены:

```bash
scripts/start_runtime_on_visionfive.sh
scripts/stop_runtime_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
```

Runtime слушает:

```text
ERPC://10.42.0.211:3000
```

### Совместимость Beremiz 1.5 И Runtime 1.4

На ПК установлен Beremiz `1.5`, на VisionFive 2 runtime `1.4`. Они различаются в eRPC stubs: поле `log_message.sec` в runtime `1.4` сериализуется как `uint32`, а клиент `1.5` ожидает `uint64`. Из-за этого CLI/IDE падали на `GetLogMessage`.

Исправление сделано без изменения системных файлов `/usr/share/beremiz`: `scripts/start_runtime_on_visionfive.sh` подключает extension `scripts/beremiz_runtime_compat_15.py` через штатный параметр `Beremiz_service.py -e`.

Extension:

- пишет `log_message.sec` как `uint64`;
- возвращает пустой log tuple вместо `None`;
- обрабатывает `ConnectionResetError`, чтобы принудительно закрытый CLI/IDE client не оставлял runtime живым, но без RPC thread.

### Project URI Для GUI

`beremiz-project/study-plc/beremiz.xml` теперь хранит:

```text
ERPC://10.42.0.211:3000
```

Это позволяет открывать GUI командой:

```bash
beremiz beremiz-project/study-plc
```

и подключаться к runtime на VisionFive 2, а не к `LOCAL://`.

### Локальные Secret/State Файлы

Beremiz может создавать `beremiz-project/*/psk/` при ERPC-подключении. Эти файлы не должны попадать в git или переноситься на плату, поэтому они исключены в `.gitignore` и `scripts/sync_to_visionfive.sh`.

## Текущий Проверенный Статус

Последняя проверка:

```text
PLC Status: Started
Modbus registers: [250, 0, 500]
```

Demo проходит:

```text
LOW       -> output_command=0
HIGH      -> output_command=1
LOW-AGAIN -> output_command=0
```

Online monitoring через CLI работает, GUI запускается в графической сессии ПК.

## Быстрый Старт

Полный порядок действий находится в [GUIDE.md](GUIDE.md). Минимальный happy path:

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

В другом терминале:

```bash
scripts/sync_to_visionfive.sh
scripts/build_on_visionfive.sh
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
/usr/bin/python3 scripts/demo_alarm_toggle.py
beremiz beremiz-project/study-plc
```
