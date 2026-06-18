# Beremiz Supervised RT Stand

Этот репозиторий содержит один Beremiz-проект для текущего стенда:

```text
Arduino -> RockPI GPIO -> controller-emu -> raw Ethernet -> VisionFive 2
        -> rt-supervisor -> /dev/shm + futex -> Beremiz PLC -> ответ обратно
```

ПК не участвует в real-time loop. Он нужен для разработки, запуска scripts, Beremiz GUI и сбора измерений.

## Узлы

| Узел | Назначение |
| --- | --- |
| ПК | Beremiz IDE/CLI, scripts, GUI monitoring, rt-tester receiver |
| VisionFive 2 `10.42.0.211` | `alt-rt-supervisor` и Beremiz runtime |
| RockPI `10.43.0.2` | `controller-emu`, GPIO input/output и raw Ethernet link |
| Arduino Mega | генерирует GPIO pulses и измеряет задержку ответа |

Сеть:

```text
ПК 10.42.0.1 <-> VisionFive end1 10.42.0.211
RockPI end0 10.43.0.2 <-> VisionFive end0 10.43.0.1
```

## Что Лежит В Репозитории

| Path | Что это |
| --- | --- |
| `beremiz-project/supervised-raw-plc/` | единственный Beremiz PLC project |
| `scripts/sync_to_visionfive.sh` | копирует репозиторий на VisionFive |
| `scripts/build_supervised_raw_on_visionfive.sh` | собирает PLC на VisionFive |
| `scripts/start_runtime_on_visionfive.sh` | временно запускает Beremiz runtime для загрузки PLC |
| `scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh` | загружает PLC в runtime |
| `scripts/install_supervised_runtime_wrapper_on_visionfive.sh` | ставит wrapper для запуска runtime из supervisor |
| `scripts/start_supervised_stack.sh` | запускает supervisor на VisionFive и controller на RockPI |
| `scripts/stop_supervised_stack.sh` | останавливает весь supervised stack |
| `scripts/sync_supervised_debug_build_from_visionfive.sh` | подтягивает `build/VARIABLES.csv` для GUI-debug |
| `scripts/check_runtime_status.py` | проверяет `PLC Status` через ERPC |

`rt-supervisor` находится здесь: https://altlinux.space/besogon1238/rt-supervisor

## PLC-Логика

RockPI отправляет в PLC значения `sensor`, `threshold` и `sequence`. PLC считает:

```iecst
alarm := sensor_value > threshold;

IF alarm THEN
    output_command := UINT#1;
ELSE
    output_command := UINT#0;
END_IF;
```

Для текущего controller profile:

| GPIO edge | `sensor_value` | `threshold` | `alarm` | `output_command` |
| --- | --- | --- | --- | --- |
| rising | `600` | `500` | `TRUE` | `1` |
| falling | `400` | `500` | `FALSE` | `0` |

Дополнительные diagnostic counters (`request_count`, `last_sequence`, `high_request_count`, `low_request_count`) нужны для GUI-наблюдения.

## Пакеты ALT Linux

Пакеты ниже проверены на текущем стенде: ПК `x86_64`, VisionFive `riscv64`, RockPI `aarch64`.

На ПК:

```bash
su - -c 'apt-get install beremiz matiec python3 python3-module-serial python3-module-requests python3-module-prometheus_client openssh-clients tar git'
```

На VisionFive 2:

```bash
apt-get install beremiz matiec python3 openssh-clients openssh-server tar git gcc make binutils glibc-devel cmake zlib-devel libgpiod-devel kernel-image-rt
```

На RockPI:

```bash
apt-get install python3 openssh-clients openssh-server tar git gcc make binutils glibc-devel cmake zlib-devel libgpiod-devel kernel-image-rt
```

`rt-supervisor` собирается отдельно из https://altlinux.space/besogon1238/rt-supervisor. Для этого нужны `cmake`, `gcc`, `zlib-devel`, `libgpiod-devel` и явный board, например `cmake -B Build -DBOARD=repkapi4`.

## Быстрый Запуск

Подробные команды находятся в [GUIDE.md](GUIDE.md). Короткий порядок:

```bash
scripts/stop_supervised_stack.sh
scripts/sync_to_visionfive.sh
scripts/build_supervised_raw_on_visionfive.sh
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh
scripts/install_supervised_runtime_wrapper_on_visionfive.sh
scripts/stop_runtime_on_visionfive.sh
TIMEOUT_US=30000000 scripts/start_supervised_stack.sh
scripts/sync_supervised_debug_build_from_visionfive.sh
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

После этого можно открывать GUI:

```bash
beremiz beremiz-project/supervised-raw-plc
```

Runtime URI:

```text
ERPC://10.42.0.211:3000
```

## Важно

- Для GUI/debug запускайте stack с `TIMEOUT_US=30000000`, иначе supervisor может перезапустить runtime во время polling.
- Вручную supervisor запускается на VisionFive так: `/root/rt-supervisor/Build/src/alt-rt-supervisor -i end0 -t 30000000 -r /root/beremiz-runtime/supervised-raw-plc/start_runtime.sh`.
- После каждой сборки PLC на VisionFive выполняйте `scripts/sync_supervised_debug_build_from_visionfive.sh`, иначе GUI не найдет локальный `build/VARIABLES.csv`.
- `alarm` меняется не от GUI и не от receiver, а от GPIO edges, которые RockPI получает на input line.
