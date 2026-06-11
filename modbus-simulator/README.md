# Modbus TCP Simulator

Минимальный simulator внешнего Modbus TCP устройства для учебного стенда Beremiz.

Зависимости: только стандартная библиотека Python 3.

## Запуск

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

Порт `1502` выбран вместо стандартного `502`, чтобы запускать simulator без root-прав.

## Карта Регистров

| Holding register | Назначение |
| --- | --- |
| `0` | `sensor_value`, имитация значения датчика |
| `1` | `output_command`, команда, которую позже будет писать PLC |
| `2` | `threshold`, порог для PLC-логики |

Начальные значения: `[123, 0, 500]`.

## Проверка Клиентом

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 write-single 1 77
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Ожидаемый результат:

```text
[123, 0, 500]
ok
[123, 77, 500]
```

## Поддержанные Modbus-Функции

- `3`: read holding registers
- `4`: read input registers
- `6`: write single holding register
- `16`: write multiple holding registers
