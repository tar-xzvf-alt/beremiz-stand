# Raw Ethernet PLC Experiment

Этот документ описывает экспериментальную ветку `experiment/raw-ethernet-plc`.

Цель: проверить сценарий, где внешнее устройство отправляет raw Ethernet packet на VisionFive 2, а PLC-логика Beremiz реагирует на полученные данные.

Текущий результат ветки: raw Ethernet packets отправляет отдельный RockPI по своему `end0` в VisionFive `end0`; Beremiz runtime на VisionFive принимает request внутри `c_ext`, PLC вычисляет `output_command`, а VisionFive отправляет raw Ethernet response обратно на RockPI. ПК остается engineering/monitoring station на VisionFive `end1`.

```text
ПК <-> VisionFive end1
  SSH / Beremiz ERPC / monitoring

RockPI end0 <-> VisionFive end0
  raw Ethernet request/response, EtherType 0x1122
```

## Выбранный Вариант

Первый MVP использовал вариант A: отдельный bridge на VisionFive 2 принимает raw Ethernet packet и перекладывает данные в существующий Modbus TCP simulator на ПК. PLC остается без изменений и продолжает читать `sensor_value`, `output_command`, `threshold` через уже настроенный Beremiz Modbus TCP client.

```text
ПК device-sender
  raw Ethernet frame, EtherType 0x1122
        |
        v
VisionFive 2 raw-ethernet-to-modbus bridge
  decode payload
  write Modbus registers on PC simulator
        |
        v
Beremiz PLC on VisionFive 2
  reads Modbus registers from PC simulator
  computes alarm/output_command
  writes output_command to Modbus register 1
```

Это был промежуточный MVP для проверки end-to-end поведения и GUI-наблюдения без изменения PLC-программы. Текущий direct raw вариант ниже уже убирает Modbus из raw Ethernet control loop.

## Почему Не Встраиваем Raw Socket Сразу В PLC

Beremiz ST-код не работает напрямую с raw sockets. Встраивание raw Ethernet внутрь runtime лучше делать отдельным этапом через Beremiz extension/confnode или shared memory. Для первого эксперимента bridge проще, безопаснее и быстрее проверяется.

## Что Берем Из `rt-supervisor`

Из `/home/taranev/work_repos/rt/rt-supervisor` переиспользуется идея, а не код целиком:

- raw Ethernet через `AF_PACKET` / `SOCK_RAW`;
- EtherType `0x1122`;
- модель отдельного устройства, которое присылает пакет контроллеру;
- дальнейшая возможность перейти к framing/CRC из `controller-conn.c`.

В MVP payload маленький и помещается в один Ethernet frame, поэтому slicing на несколько пакетов и CRC trailer пока не нужны.

## Формат Пакета MVP

EtherType: `0x1122`.

Payload, network byte order:

| Field | Type | Meaning |
| --- | --- | --- |
| `magic` | `4s` | ASCII `BETH` |
| `version` | `u8` | `1` |
| `sequence` | `u32` | sender sequence number |
| `sensor_value` | `u16` | value for Modbus register `0` |
| `threshold` | `u16` | value for Modbus register `2` |
| `forced_output` | `u16` | value deliberately written to Modbus register `1` before PLC corrects it |

Bridge behavior:

1. Receive raw Ethernet frame on VisionFive 2 interface `end1`.
2. Validate EtherType and payload magic/version.
3. Write `threshold` to Modbus holding register `2` on `10.42.0.1:1502`.
4. Write `forced_output` to Modbus holding register `1`.
5. Write `sensor_value` to Modbus holding register `0`.
6. PLC reads the new registers and overwrites register `1` with computed `output_command`.

## Demo

```text
LOW:  raw packet sensor=400 threshold=500 forced_output=1 -> PLC writes register 1 = 0
HIGH: raw packet sensor=600 threshold=500 forced_output=0 -> PLC writes register 1 = 1
LOW:  raw packet sensor=250 threshold=500 forced_output=1 -> PLC writes register 1 = 0
```

Фактически проверено на стенде:

- ПК sender interface: `enp2s0` (`10.42.0.1`).
- VisionFive 2 bridge interface: `end1` (`10.42.0.211`).
- Beremiz runtime URI: `ERPC://10.42.0.211:3000`.
- Modbus simulator: `10.42.0.1:1502`.

Подготовка:

```bash
./scripts/sync_to_visionfive.sh
./scripts/start_runtime_on_visionfive.sh
./scripts/deploy_run_on_visionfive_runtime.sh
./scripts/start_raw_eth_bridge_on_visionfive.sh
```

Запуск demo на ПК требует root/CAP_NET_RAW для raw socket:

```bash
sudo /usr/bin/python3 scripts/demo_raw_ethernet_alarm.py --interface enp2s0
```

Успешный результат:

```text
LOW: sent=29 sequence=1 sensor=400 threshold=500 forced_output=1 final=[400, 0, 500]
HIGH: sent=29 sequence=2 sensor=600 threshold=500 forced_output=0 final=[600, 1, 500]
LOW-AGAIN: sent=29 sequence=3 sensor=250 threshold=500 forced_output=1 final=[250, 0, 500]
raw Ethernet demo passed
```

Bridge log показывает состояние сразу после записи raw-пакета в Modbus. Demo затем ждет, пока PLC прочитает регистры и перезапишет register `1` вычисленным `output_command`.

## Initial Planned Files

```text
raw-ethernet/send_raw_packet.py          # PC-side device sender
scripts/raw_eth_to_modbus_bridge.py      # VisionFive 2 bridge
scripts/start_raw_eth_bridge_on_visionfive.sh
scripts/demo_raw_ethernet_alarm.py
```

## Initial Branch Workflow

```bash
git switch -c experiment/raw-ethernet-plc
```

Каждый завершенный шаг коммитится отдельно в этой ветке.

## Direct Raw Ethernet Runtime Variant

Следующий архитектурный шаг убирает Modbus simulator из raw Ethernet цепочки. Для этого добавлен отдельный Beremiz project variant: `beremiz-project/direct-raw-plc`.

Схема:

```text
device sender
  raw Ethernet frame, EtherType 0x1122
        |
        v
VisionFive 2 Beremiz runtime
  c_ext raw socket receiver
  updates external PLC variables directly
        |
        v
PLC ST logic computes alarm/output_command
```

В этом варианте не используются:

- внешний `scripts/raw_eth_to_modbus_bridge.py`;
- Modbus TCP simulator;
- Beremiz Modbus client confnode.

Ключевые файлы:

```text
beremiz-project/direct-raw-plc/                 # отдельный direct raw project
beremiz-project/direct-raw-plc/c_ext_0@c_ext/   # C extension с raw receiver thread
scripts/build_direct_raw_on_visionfive.sh
scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
scripts/demo_direct_raw_ethernet.py
```

Первичная проверка direct raw project выполнялась с ПК как временным sender. Это больше не целевой control loop, но полезно как smoke-test без RockPI:

```bash
./scripts/sync_to_visionfive.sh
./scripts/build_direct_raw_on_visionfive.sh
./scripts/stop_raw_eth_bridge_on_visionfive.sh
./scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
./scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end1
./scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
```

Отправка raw Ethernet packets с ПК:

```bash
sudo /usr/bin/python3 raw-ethernet/send_raw_packet.py --interface enp2s0 --sequence 1 --sensor 400 --threshold 500 --forced-output 1
sudo /usr/bin/python3 raw-ethernet/send_raw_packet.py --interface enp2s0 --sequence 2 --sensor 600 --threshold 500 --forced-output 0
sudo /usr/bin/python3 raw-ethernet/send_raw_packet.py --interface enp2s0 --sequence 3 --sensor 250 --threshold 500 --forced-output 1
```

Проверенный runtime log на VisionFive 2:

```text
direct raw receiver listening on end1, EtherType=0x1122
direct raw recv seq=1 sensor=400 threshold=500 forced_output=1
direct raw plc seq=1 sensor=400 threshold=500 forced_output=1 output=0
direct raw recv seq=2 sensor=600 threshold=500 forced_output=0
direct raw plc seq=2 sensor=600 threshold=500 forced_output=0 output=1
direct raw recv seq=3 sensor=250 threshold=500 forced_output=1
direct raw plc seq=3 sensor=250 threshold=500 forced_output=1 output=0
```

Это подтверждает прямую цепочку `raw Ethernet -> Beremiz runtime c_ext -> PLC logic` без промежуточного Modbus слоя.

Автоматическая проверка direct raw path:

```bash
sudo /usr/bin/python3 scripts/demo_direct_raw_ethernet.py --interface enp2s0
```

Скрипт отправляет три raw Ethernet packets, читает runtime log на VisionFive 2 через SSH и проверяет, что PLC output стал `0`, `1`, `0`.

Успешный результат:

```text
LOW: sent=29 sequence=1781465089 sensor=400 threshold=500 forced_output=1 output=0
HIGH: sent=29 sequence=1781465090 sensor=600 threshold=500 forced_output=0 output=1
LOW-AGAIN: sent=29 sequence=1781465091 sensor=250 threshold=500 forced_output=1 output=0
direct raw Ethernet demo passed
```

## RockPI Request/Response Variant

Текущая целевая схема переносит sender с ПК на RockPI и добавляет raw Ethernet response от VisionFive обратно на устройство:

```text
RockPI end0, 10.43.0.2/24
  device-controller/controller-once
  raw Ethernet v2 request
        |
        v
VisionFive end0, 10.43.0.1/24
  Beremiz runtime direct-raw-plc
  c_ext receives request
  PLC computes output_command
  c_ext sends raw Ethernet v2 response
        |
        v
RockPI receives response
```

ПК подключен к VisionFive по `end1` (`10.42.0.211/24`) и используется только для SSH/ERPC/monitoring.

Protocol v2 payload, network byte order:

| Field | Type | Request Meaning | Response Meaning |
| --- | --- | --- | --- |
| `magic` | `4s` | `BETH` | `BETH` |
| `version` | `u8` | `2` | `2` |
| `msg_type` | `u8` | `1=request` | `2=response` |
| `sequence` | `u32` | request id | echoed request id |
| `value0` | `u16` | `sensor_value` | `output_command` |
| `value1` | `u16` | `threshold` | `status` |
| `value2` | `u16` | `forced_output` | reserved |

Ключевые файлы:

```text
device-controller/controller-once.c
device-controller/controller-loop.c
device-controller/raw_proto.h
scripts/configure_rockpi_link_on_visionfive.sh
scripts/start_direct_raw_runtime_on_visionfive.sh
ROCKPI_CONTROLLER_PLAN.md
```

Проверенный запуск:

```bash
./scripts/configure_rockpi_link_on_visionfive.sh
./scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
./scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
./scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-once -i end0 --sequence 2003 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000"'
```

Проверенный результат на RockPI:

```text
sent request seq=2003 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=2003 output=1 status=0
```

Runtime log на VisionFive:

```text
direct raw receiver listening on end0, EtherType=0x1122
direct raw recv request seq=2003 sensor=600 threshold=500 forced_output=0
direct raw plc seq=2003 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=2003 output=1 status=0
```

Проверенный `controller-loop` без GPIO:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-loop -i end0 --sequence 3000 --count 6 --period-ms 200 --timeout-ms 2000"'
```

Результат:

```text
cycle=1 seq=3000 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=2 seq=3001 sensor=600 threshold=500 forced_output=0 output=1 status=0
cycle=3 seq=3002 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=4 seq=3003 sensor=600 threshold=500 forced_output=0 output=1 status=0
cycle=5 seq=3004 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=6 seq=3005 sensor=600 threshold=500 forced_output=0 output=1 status=0
```

Следующий практический этап: GPIO edge -> request -> response -> GPIO output.
