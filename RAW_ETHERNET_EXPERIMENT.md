# Raw Ethernet PLC Experiment

Этот документ описывает экспериментальную ветку `experiment/raw-ethernet-plc`.

Цель: проверить сценарий, где внешнее устройство отправляет raw Ethernet packet на VisionFive 2, а PLC-логика Beremiz реагирует на полученные данные.

## Выбранный Вариант

Используется вариант A: отдельный bridge на VisionFive 2 принимает raw Ethernet packet и перекладывает данные в существующий Modbus TCP simulator на ПК. PLC остается без изменений и продолжает читать `sensor_value`, `output_command`, `threshold` через уже настроенный Beremiz Modbus TCP client.

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

Это не финальная глубокая интеграция raw Ethernet в Beremiz runtime. Это MVP для проверки end-to-end поведения и GUI-наблюдения без изменения PLC-программы.

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

## Planned Files

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
ПК device-sender
  raw Ethernet frame, EtherType 0x1122
        |
        v
VisionFive 2 Beremiz runtime
  c_ext raw socket receiver on end1
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

Подготовка и запуск direct raw project:

```bash
./scripts/sync_to_visionfive.sh
./scripts/build_direct_raw_on_visionfive.sh
./scripts/stop_raw_eth_bridge_on_visionfive.sh
./scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/study-plc
./scripts/start_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc 10.42.0.211 3000
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
