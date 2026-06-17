# Beremiz Project

В каталоге лежат три Beremiz project variants:

- `study-plc/`: базовый Modbus TCP project.
- `direct-raw-plc/`: экспериментальный raw Ethernet project для RockPI/VisionFive схемы без Modbus в control loop.
- `supervised-raw-plc/`: experimental project для запуска Beremiz runtime как child `rt-supervisor`, с обменом через `/dev/shm` + futex.

`study-plc/` создан штатным API установленного Beremiz (`ProjectController.NewProject`) и является начальным PLC-проектом стенда.

Открытие в IDE:

```bash
beremiz beremiz-project/study-plc
```

Проект хранит remote runtime URI в `beremiz.xml`:

```text
ERPC://10.42.0.211:3000
```

CLI-проверка загрузки проекта:

```bash
/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc clean
```

`build/` внутри проекта является рабочим каталогом Beremiz и не хранится в git.

## Study PLC

`study-plc` настроен как Modbus TCP client к simulator на ПК:

- remote host: `10.42.0.1`
- remote port: `1502`
- cycle task: `task0`, `T#100ms`

PLC-логика в `plc_prg`:

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

Modbus map:

| Simulator holding register | PLC variable | IEC location | Direction |
| --- | --- | --- | --- |
| `0` | `SensorRegister` / `sensor_value` | `%IW0.0.0.0` | read |
| `1` | `RemoteOutputRegister` / `remote_output_echo` | `%IW0.0.0.1` | read |
| `2` | `ThresholdRegister` / `threshold` | `%IW0.0.0.2` | read |
| `1` | `OutputCommandRegister` / `output_command` | `%QW0.0.1.1` | write |

Build with Modbus support:

```bash
scripts/prepare_modbus_source.sh
MODBUS_PATH="$PWD/.deps/Modbus" /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc clean build
```

Build on VisionFive 2:

```bash
scripts/sync_to_visionfive.sh
scripts/build_on_visionfive.sh
```

Runtime smoke test from VisionFive 2 to the PC simulator:

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

In another terminal:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 0 600
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 1 0
ssh root@10.42.0.211 'cd /root/beremiz-stand && MODBUS_PATH="/root/beremiz-stand/.deps/Modbus" timeout 30s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --keep transfer run'
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Expected final register state: `[600, 1, 500]`.

Persistent runtime on VisionFive 2:

```bash
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

Online monitoring check from the PC with the stock Beremiz CLI:

```bash
/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --uri ERPC://10.42.0.211:3000 --keep connect
```

Stop persistent runtime:

```bash
scripts/stop_runtime_on_visionfive.sh
```

The runtime URI is `ERPC://10.42.0.211:3000`.

`scripts/start_runtime_on_visionfive.sh` loads `scripts/beremiz_runtime_compat_15.py` on VisionFive 2 when the file is present. This keeps the Beremiz 1.4 runtime eRPC log messages compatible with the Beremiz 1.5 CLI/IDE on the PC.

Useful variables for IDE online monitoring:

| Variable | Expected value when simulator registers are `[600, 1, 500]` |
| --- | --- |
| `sensor_value` | `600` |
| `threshold` | `500` |
| `remote_output_echo` | `1` |
| `alarm` | `TRUE` |
| `output_command` | `1` |
| `SensorRegister` | `16#0258` |
| `ThresholdRegister` | `16#01F4` |
| `OutputCommandRegister` | `16#0001` |

Alarm toggle demo:

```bash
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
/usr/bin/python3 scripts/demo_alarm_toggle.py
```

The demo forces Modbus register `1` to the wrong value before each case, then waits until the PLC overwrites it with the expected `output_command`.

## Direct Raw PLC

`direct-raw-plc` использует ту же учебную логику `alarm := sensor_value > threshold`, но входы приходят не из Modbus, а из raw Ethernet receiver внутри Beremiz `c_ext`.

Measurement profile:

- cycle task: `task0`, `T#1ms`;
- raw receiver thread: `SCHED_FIFO`, priority `80`;
- PLC task thread: `SCHED_FIFO`, priority `85`;
- raw Ethernet request/response: one padded `1514` byte frame per direction, with protocol v2 in the first `16` payload bytes;
- runtime raw request/response logging disabled with `#if 0` blocks in `c_ext_0@c_ext/cfile.xml`.

Схема runtime:

```text
RockPI end0
  controller-once / controller-loop / controller-gpio-loop
  raw Ethernet v2 request
        |
        v
VisionFive end0
  Beremiz runtime direct-raw-plc
  c_ext raw socket receiver
  PLC ST logic
  c_ext raw Ethernet response
        |
        v
RockPI end0
```

External variables, объявленные в `c_ext_0@c_ext/cfile.xml`:

| Variable | Direction in PLC logic | Meaning |
| --- | --- | --- |
| `RawSensorValue` | input | `sensor_value` from raw request |
| `RawThreshold` | input | threshold from raw request |
| `RawForcedOutput` | input | remote echo/test value from raw request |
| `RawSequence` | input | request sequence id |
| `RawOutputCommand` | output | PLC-computed output sent in raw response |

Build on VisionFive 2:

```bash
scripts/sync_to_visionfive.sh
scripts/build_direct_raw_on_visionfive.sh
```

Run with raw receiver on VisionFive `end0`:

```bash
scripts/configure_rockpi_link_on_visionfive.sh
scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
```

Verified RockPI once exchange:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-once -i end0 --sequence 2003 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000"'
```

Expected response:

```text
received response seq=2003 output=1 status=0
```

Verified RockPI loop without GPIO:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-loop -i end0 --sequence 3000 --count 6 --period-ms 200 --timeout-ms 2000"'
```

Expected alternating outputs: `0, 1, 0, 1, 0, 1`.

GPIO controller target on RockPI:

```bash
scripts/deploy_controller_to_rockpi.sh
scripts/build_controller_on_rockpi.sh
```

Default GPIO mapping is `/dev/gpiochip4`, input line `6`, output line `7`. `controller-gpio-loop` uses `SCHED_FIFO` priority `80`, locks memory with `mlockall`, sets the RockPI GPIO IRQ thread to `SCHED_FIFO` priority `99`, and has per-cycle logging disabled for measurement. On send/timeout error it leaves output line `7` unchanged.

Use `scripts/run_controller_once_on_rockpi.sh`, `scripts/run_controller_loop_on_rockpi.sh`, and `scripts/run_controller_gpio_loop_on_rockpi.sh` sequentially. Do not run multiple raw controller programs on RockPI `end0` at the same time.

## Supervised Raw PLC

`supervised-raw-plc` использует ту же учебную ST-логику `alarm := sensor_value > threshold`, но transport переносится в штатную архитектуру `rt-supervisor`.

Схема runtime:

```text
RockPI rt-supervisor/controller-emu
  BETH v2 request in first 16 bytes of controller_msg_t.payload
        |
        v
VisionFive alt-rt-supervisor
  raw Ethernet fragmentation/reassembly, CRC, watchdog
  /dev/shm/shmem_input + /dev/shm/shmem_output + futex
        |
        v
Beremiz runtime supervised-raw-plc
  c_ext reads shmem input in __retrieve
  PLC ST logic computes output_command
  c_ext writes shmem output in __publish
```

Measurement profile:

- cycle task: `task0`, `T#1ms`;
- PLC task thread: `SCHED_FIFO`, priority `92`;
- `alt-rt-supervisor`: `SCHED_FIFO`, priority `88`;
- RockPI `controller-emu` RT thread: `SCHED_FIFO`, priority `85`;
- Ethernet IRQ priorities are set by `/root/pin_visionfive_supervised.sh` and `/root/pin_rockpi_controller.sh`;
- supervisor payload: existing `rt-supervisor` logical payload, `96 KiB`;
- protocol v2 fields: first `16` bytes of the logical payload;
- Beremiz runtime does not open raw Ethernet sockets in this variant.

External variables, declared in `c_ext_0@c_ext/cfile.xml`:

| Variable | Direction in PLC logic | Meaning |
| --- | --- | --- |
| `RawSensorValue` | input | `sensor_value` from supervised request |
| `RawThreshold` | input | threshold from supervised request |
| `RawForcedOutput` | input | remote echo/test value from supervised request |
| `RawSequence` | input | request sequence id |
| `RawOutputCommand` | output | PLC-computed output sent in supervised response |

Build on VisionFive 2:

```bash
scripts/sync_to_visionfive.sh
scripts/build_supervised_raw_on_visionfive.sh
```

Install/update runtime wrapper:

```bash
scripts/install_supervised_runtime_wrapper_on_visionfive.sh
```

The wrapper is installed as `/root/beremiz-runtime/supervised-raw-plc/start_runtime.sh` and is intended for `alt-rt-supervisor -r`.

Deploy PLC into the runtime directory using a temporary standalone Beremiz service:

```bash
scripts/start_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/supervised-raw-plc 10.42.0.211 3000
scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh
scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/supervised-raw-plc
```

Run under `rt-supervisor`:

```bash
ssh root@10.42.0.211 '/root/rt-supervisor/Build/src/alt-rt-supervisor -i end0 -t 5000000 -r /root/beremiz-runtime/supervised-raw-plc/start_runtime.sh'
ssh root@10.42.0.211 '/root/pin_visionfive_supervised.sh'
ssh root@10.42.0.211 'ssh root@10.43.0.2 "/root/pin_rockpi_controller.sh"'
```
