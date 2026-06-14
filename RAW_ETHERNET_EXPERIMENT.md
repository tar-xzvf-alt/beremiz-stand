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

## Expected Demo

```text
LOW:  raw packet sensor=400 threshold=500 forced_output=1 -> PLC writes register 1 = 0
HIGH: raw packet sensor=600 threshold=500 forced_output=0 -> PLC writes register 1 = 1
LOW:  raw packet sensor=250 threshold=500 forced_output=1 -> PLC writes register 1 = 0
```

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
