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
| `scripts/stand.py` | единая CLI точка входа для всех операций стенда |
| `scripts/*.sh` | compatibility wrappers, передающие вызов в `stand.py` |
| `scripts/check_runtime_status.py` | проверяет `PLC Status` через ERPC |
| `profiles/visionfive-rockpi.conf` | конфигурация стенда (IP, пути, board names) |

`rt-supervisor` находится здесь: https://altlinux.space/besogon1238/rt-supervisor

Полезные разделы `rt-supervisor`:

- `docs/runtime-abi.md`: shared memory/futex contract между supervisor и runtime;
- `docs/boards.md`: GPIO profiles и добавление новых плат;
- `docs/altlinux-packages.md`: проверенные пакеты ALT Linux;
- `docs/beremiz-runtime.md`: запуск Beremiz runtime через `alt-rt-supervisor -r`.
- `docs/install-deploy.md`: source tree deploy и optional `cmake --install` layout.

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

`rt-supervisor` собирается отдельно из https://altlinux.space/besogon1238/rt-supervisor. Точные пакеты и board profiles описаны в `docs/altlinux-packages.md` и `docs/boards.md` этого репозитория.

## Быстрый Запуск

Для обычного пользователя сначала смотрите [QUICKSTART.md](QUICKSTART.md): там
описан запуск через единый `scripts/stand.py`.

Подробные ручные команды находятся в [GUIDE.md](GUIDE.md). Короткий порядок
через `stand.py`:

```bash
scripts/stand.py stop
scripts/stand.py sync-stand
scripts/stand.py build-plc
scripts/stand.py start-runtime
scripts/stand.py deploy-plc
scripts/stand.py install-runtime-wrapper
scripts/stand.py stop-runtime
TIMEOUT_US=30000000 scripts/stand.py start
scripts/stand.py sync-plc-debug-build
scripts/stand.py check
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
- Вручную supervisor запускается на VisionFive так: `/root/rt-supervisor/scripts/run_supervisor.sh end0 30000000 /root/beremiz-runtime/supervised-raw-plc/start_runtime.sh /root/rt-supervisor/Build/src/alt-rt-supervisor`.
- Вручную controller запускается на RockPI так: `/root/rt-supervisor/scripts/run_controller.sh end0 /root/rt-supervisor/Build/src/controller-emu`.
- После каждой сборки PLC на VisionFive выполняйте `scripts/sync_supervised_debug_build_from_visionfive.sh`, иначе GUI не найдет локальный `build/VARIABLES.csv`.
- `alarm` меняется не от GUI и не от receiver, а от GPIO edges, которые RockPI получает на input line.
- Схема сети, SSH-доступ и восстановление internet routing для VisionFive/RockPI описаны в [NETWORK.md](NETWORK.md).
- План упаковки `rt-controller`, `rt-supervisor`, `rt-tester` и helper-пакета стенда описан в [ROADMAP.md](ROADMAP.md).
