# Beremiz Project

`study-plc/` создан штатным API установленного Beremiz (`ProjectController.NewProject`) и является начальным пустым PLC-проектом стенда.

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
