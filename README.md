# Учебный Стенд Beremiz На Linux-Контроллере

Репозиторий содержит учебный стенд для изучения Beremiz на Linux-контроллере. Базовый сценарий использует `Starfive VisionFive 2` как PLC и Modbus TCP simulator на ПК. Экспериментальная ветка `experiment/raw-ethernet-plc` дополнительно содержит direct raw Ethernet схему, где отдельный RockPI отправляет raw Ethernet request на VisionFive и получает raw Ethernet response от PLC.

Пошаговый запуск вынесен в [GUIDE.md](GUIDE.md).

## Суть Стенда

Стенд показывает полный цикл работы Linux PLC:

- разработка проекта Beremiz на ПК;
- нативная сборка PLC на `riscv64` плате VisionFive 2;
- запуск `Beremiz_service.py` как persistent runtime на плате;
- базовый обмен PLC с внешним устройством по Modbus TCP;
- экспериментальный обмен `RockPI -> raw Ethernet -> VisionFive PLC -> raw Ethernet response -> RockPI` без Modbus в control loop;
- online monitoring с ПК через ERPC;
- демонстрация переключения `alarm` и `output_command` при изменении входного значения датчика.

Базовая Modbus-архитектура:

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

Экспериментальная raw Ethernet архитектура в текущей ветке:

```text
ПК разработчика
  SSH / Beremiz ERPC / monitoring
        |
        | VisionFive end1, 10.42.0.211/24
        v
Starfive VisionFive 2
  Beremiz runtime, direct-raw-plc
  c_ext raw Ethernet receiver/responder on end0
        ^
        | raw Ethernet request/response, EtherType 0x1122
        v
RockPI end0, 10.43.0.2/24
  device-controller/controller-once / controller-loop / controller-gpio-loop
```

В этой схеме ПК не участвует в control loop: он только запускает, загружает и наблюдает стенд.

## Что Реализовано

Основные артефакты:

| Path | Назначение |
| --- | --- |
| `beremiz-project/study-plc/` | Beremiz PLC project |
| `beremiz-project/direct-raw-plc/` | Beremiz PLC project с raw Ethernet `c_ext` без Modbus |
| `device-controller/controller-once.c` | RockPI-side одиночный raw Ethernet request/response tool |
| `device-controller/controller-loop.c` | RockPI-side циклический request/response tool без GPIO |
| `device-controller/controller-gpio-loop.c` | RockPI-side GPIO edge -> raw request -> GPIO output loop |
| `modbus-simulator/modbus_server.py` | Modbus TCP simulator на стандартной библиотеке Python |
| `modbus-simulator/modbus_client.py` | Утилита чтения/записи Modbus registers |
| `scripts/sync_to_visionfive.sh` | Передача репозитория на VisionFive 2 через `scp` |
| `scripts/build_on_visionfive.sh` | Нативная сборка PLC на VisionFive 2 |
| `scripts/start_runtime_on_visionfive.sh` | Запуск persistent Beremiz runtime на плате |
| `scripts/deploy_run_on_visionfive_runtime.sh` | Transfer/run PLC в уже запущенный runtime |
| `scripts/check_runtime_status.py` | Проверка ERPC runtime без чтения runtime logs |
| `scripts/demo_alarm_toggle.py` | Демонстрация переключения alarm/output |
| `scripts/demo_direct_raw_ethernet.py` | PC-side проверка direct raw path до появления RockPI |
| `scripts/configure_rockpi_link_on_visionfive.sh` | Настройка VisionFive `end0` для линка с RockPI |
| `scripts/start_direct_raw_runtime_on_visionfive.sh` | Запуск Beremiz runtime с `RAW_ETH_INTERFACE=end0` |
| `scripts/deploy_controller_to_rockpi.sh` | Передача `device-controller/` на RockPI через VisionFive |
| `scripts/build_controller_on_rockpi.sh` | Сборка `controller-once`, `controller-loop`, `controller-gpio-loop` на RockPI |
| `scripts/run_controller_once_on_rockpi.sh` | Проверка одиночного RockPI raw Ethernet exchange |
| `scripts/run_controller_loop_on_rockpi.sh` | Проверка циклического RockPI raw Ethernet loop без GPIO |
| `scripts/run_controller_gpio_loop_on_rockpi.sh` | Запуск GPIO-driven RockPI controller loop |
| `scripts/beremiz_runtime_compat_15.py` | Runtime compatibility layer для Beremiz 1.5 client -> 1.4 runtime |
| `beremiz-modbus-source-20170318-alt1.noarch.rpm` | Offline RPM с Modbus C sources |

## PLC-Логика

В обоих вариантах используется одна и та же учебная логика:

Modbus simulator хранит три holding registers:

| Register | Назначение |
| --- | --- |
| `0` | `sensor_value` |
| `1` | `output_command` |
| `2` | `threshold` |

`study-plc` каждые `100 ms` читает Modbus registers `0..2`, вычисляет alarm и пишет результат в register `1`. `direct-raw-plc` использует ту же логику, но в измерительном профиле работает с period `T#10ms` и получает входы из raw Ethernet `c_ext`.

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

В `study-plc` входы/выходы приходят через Modbus registers. В `direct-raw-plc` входы приходят из raw Ethernet request через `c_ext`, а `output_command` отправляется обратно как raw Ethernet response.

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

Базовый Modbus path проверен:

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

Direct raw RockPI path проверен:

```text
RockPI end0 -> VisionFive end0 -> Beremiz direct-raw-plc -> response -> RockPI end0
```

Проверенный вывод на RockPI:

```text
sent request seq=2003 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=2003 output=1 status=0
```

Ранее runtime log на VisionFive показывал raw request/response строки:

```text
direct raw receiver listening on end0, EtherType=0x1122
direct raw recv request seq=2003 sensor=600 threshold=500 forced_output=0
direct raw plc seq=2003 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=2003 output=1 status=0
```

Циклический RockPI loop без GPIO также проверен: 6 cycles с чередованием `sensor=400/600` вернули outputs `0,1,0,1,0,1`.

GPIO controller собран на RockPI как отдельный target `make controller-gpio-loop`. Измерительный path теперь quiet: штатный per-cycle logging в `controller-gpio-loop` и VisionFive `direct-raw-plc` `c_ext` отключен, чтобы не влиять на timing. Smoke-test запуска без внешнего импульса подтверждает захват `/dev/gpiochip4` lines `6/7` и cleanup отсутствием stale process; полный functional test требует физический edge на input line `6`.

RT profile для измерений:

- RockPI `controller-gpio-loop`: `SCHED_FIFO`, priority `80`, `mlockall(MCL_CURRENT | MCL_FUTURE)`.
- VisionFive raw receiver thread: `SCHED_FIFO`, priority `80`, `mlockall(...)`.
- VisionFive PLC task thread: `SCHED_FIFO`, priority `85`, `mlockall(...)`.
- `direct-raw-plc` task period: `T#10ms`.
- При send/timeout error `controller-gpio-loop` оставляет output line `7` без изменения, чтобы Arduino/rt-tester сам зафиксировал отсутствие ожидаемого edge.

Не запускайте одновременно несколько RockPI controller programs на одном `end0`/EtherType `0x1122`: два raw socket consumers могут конкурировать за response frames. Проверки `controller-once`, `controller-loop` и `controller-gpio-loop` запускаются последовательно.

## Быстрый Старт

Полный порядок действий находится в [GUIDE.md](GUIDE.md).

Минимальный Modbus happy path:

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

Минимальный direct raw RockPI path после синхронизации проекта:

```bash
scripts/configure_rockpi_link_on_visionfive.sh
scripts/build_direct_raw_on_visionfive.sh
scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-once -i end0 --sequence 2003 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000"'
```
