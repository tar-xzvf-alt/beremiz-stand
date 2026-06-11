# Beremiz Project

`study-plc/` создан штатным API установленного Beremiz (`ProjectController.NewProject`) и является начальным пустым PLC-проектом стенда.

Открытие в IDE:

```bash
beremiz beremiz-project/study-plc
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
