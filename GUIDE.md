# Пошаговое Руководство

Это практическая инструкция по запуску учебного стенда Beremiz. Базовый сценарий использует ПК разработчика, VisionFive 2 как Linux PLC-контроллер и Modbus TCP simulator на ПК. Экспериментальная raw Ethernet схема использует RockPI как отдельный отправитель request packets на VisionFive.

## 1. Проверить Схему Стенда

Адреса, используемые в проекте:

| Узел | Адрес |
| --- | --- |
| ПК разработчика | `10.42.0.1` |
| VisionFive 2 | `10.42.0.211` |
| Beremiz runtime на VisionFive 2 | `ERPC://10.42.0.211:3000` |
| Modbus simulator на ПК | `10.42.0.1:1502` |
| VisionFive `end0` для RockPI | `10.43.0.1/24` |
| RockPI `end0` | `10.43.0.2/24` |

Проверка связи с платой:

```bash
ping -c 3 10.42.0.211
ssh root@10.42.0.211 true
```

Для raw Ethernet/RockPI схемы `end1` на VisionFive остается для ПК, а `end0` используется только для point-to-point линка с RockPI.

## 2. Запустить Modbus TCP Simulator

Из корня репозитория:

```bash
python3 modbus-simulator/modbus_server.py --host 0.0.0.0 --port 1502 --verbose
```

В другом терминале проверьте registers:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Карта registers:

| Register | Назначение |
| --- | --- |
| `0` | `sensor_value` |
| `1` | `output_command` |
| `2` | `threshold` |

## 3. Синхронизировать Проект На VisionFive 2

VisionFive 2 не использует `git pull`: файлы передаются с ПК напрямую через `scp`.

```bash
scripts/sync_to_visionfive.sh
```

Скрипт распаковывает рабочую копию в `/root/beremiz-stand` на плате и не переносит `.git`, `.deps`, `build/`, `psk/` и Python cache.

## 4. Собрать PLC На VisionFive 2

Сборка выполняется нативно на `riscv64`, чтобы получить правильный `study-plc.so`.

```bash
scripts/build_on_visionfive.sh
```

Ожидаемый финал:

```text
Successfully built.
```

## 5. Запустить Persistent Runtime

```bash
scripts/start_runtime_on_visionfive.sh
```

Ожидаемый вывод:

```text
Beremiz runtime started on 10.42.0.211:3000
```

Остановить runtime:

```bash
scripts/stop_runtime_on_visionfive.sh
```

Проверить статус runtime:

```bash
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

## 6. Загрузить И Запустить PLC

```bash
scripts/deploy_run_on_visionfive_runtime.sh
```

Ожидаемые строки:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
PLC data transfered successfully.
PLC installed successfully.
Starting PLC
```

## 7. Проверить Логику Alarm

Запустите демонстрационный сценарий:

```bash
/usr/bin/python3 scripts/demo_alarm_toggle.py
```

Ожидаемый результат:

```text
LOW: sensor=400, threshold=500, forced_output=1, initial=[400, 1, 500], final=[400, 0, 500]
HIGH: sensor=600, threshold=500, forced_output=0, initial=[600, 0, 500], final=[600, 1, 500]
LOW-AGAIN: sensor=250, threshold=500, forced_output=1, initial=[250, 1, 500], final=[250, 0, 500]
demo passed
```

Смысл проверки: demo специально записывает register `1` в неправильное значение, а PLC должен исправить его в следующем цикле.

## 8. Открыть Beremiz GUI

На ПК:

```bash
beremiz beremiz-project/study-plc
```

В проекте уже сохранен runtime URI:

```text
ERPC://10.42.0.211:3000
```

Если IDE не подключилась автоматически, подключитесь к PLC runtime с этим URI. Runtime должен быть уже запущен на VisionFive 2.

## 9. Что Смотреть В Online View

Откройте `plc_prg` и наблюдайте переменные:

| Variable | LOW | HIGH | LOW-AGAIN |
| --- | --- | --- | --- |
| `sensor_value` | `400` | `600` | `250` |
| `threshold` | `500` | `500` | `500` |
| `remote_output_echo` | `0` | `1` | `0` |
| `alarm` | `FALSE` | `TRUE` | `FALSE` |
| `output_command` | `0` | `1` | `0` |
| `SensorRegister` | `16#0190` | `16#0258` | `16#00FA` |
| `ThresholdRegister` | `16#01F4` | `16#01F4` | `16#01F4` |
| `OutputCommandRegister` | `16#0000` | `16#0001` | `16#0000` |

Удобный порядок ручной проверки:

1. Запустить simulator.
2. Запустить runtime на VisionFive 2.
3. Выполнить `scripts/deploy_run_on_visionfive_runtime.sh`.
4. Открыть `beremiz beremiz-project/study-plc`.
5. Подключиться к runtime `ERPC://10.42.0.211:3000`.
6. Открыть `plc_prg` в online view.
7. В другом терминале запускать `/usr/bin/python3 scripts/demo_alarm_toggle.py`.
8. Наблюдать, как `alarm` и `output_command` меняются при переходе `sensor_value` ниже/выше `threshold`.

## 10. Проверить Online Monitoring Из CLI

Если GUI нужно исключить из диагностики, проверьте тот же ERPC monitoring через CLI:

```bash
timeout 5s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py --project-home beremiz-project/study-plc --keep connect
```

Ожидаемые признаки успеха:

```text
ERPC connecting to URI : ERPC://10.42.0.211:3000
PLC Status: Started
Debugger ready
Press Ctrl+C to quit
PLC Status: Started
```

Код `124` от `timeout` в этой проверке нормален: команда удерживает monitoring loop, а `timeout` просто завершает его через заданное время.

## 11. Как Работает PLC-Логика

PLC-программа в `plc_prg` циклически читает Modbus registers:

```iecst
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

Beremiz Modbus client читает holding registers `0..2` из simulator и пишет `output_command` обратно в holding register `1`.

## 12. Direct Raw Ethernet С RockPI

Этот раздел относится к ветке `experiment/raw-ethernet-plc`. В нем ПК не является отправителем control packets. ПК только управляет стендом через VisionFive `end1`, а raw Ethernet обмен идет по отдельному линку:

```text
RockPI end0 <-> VisionFive end0
```

### 12.1. Настроить Link VisionFive `end0`

На ПК из корня репозитория:

```bash
scripts/configure_rockpi_link_on_visionfive.sh
```

Ожидаемый адрес на VisionFive:

```text
end0: 10.43.0.1/24
```

RockPI должен иметь:

```text
end0: 10.43.0.2/24
```

RockPI console доступна через serial:

```bash
tio -b 1500000 /dev/ttyUSB0
```

### 12.2. Собрать И Запустить Direct Raw PLC

Синхронизировать и собрать direct raw project на VisionFive:

```bash
scripts/sync_to_visionfive.sh
scripts/build_direct_raw_on_visionfive.sh
```

Запустить runtime так, чтобы raw receiver слушал VisionFive `end0`:

```bash
scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
```

Проверить, что PLC started:

```bash
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
```

В measurement profile штатный raw Ethernet logging в runtime отключен. Поэтому после deploy проверяйте runtime status через ERPC, а не наличие строк `direct raw recv ...` в log.

Для проверки RT priorities на VisionFive:

```bash
ssh root@10.42.0.211 'pid=$(cat /root/beremiz-runtime/direct-raw-plc/beremiz_service.pid); ps -T -p "$pid" -o pid,tid,cls,rtprio,comm'
```

Ожидаемые RT threads после запуска PLC: один thread `FF 80` для raw receiver и один thread `FF 85` для PLC task.

Текущий measurement profile использует padded raw Ethernet frames: один request frame и один response frame по `1514 bytes` каждый. Логика PLC с `sensor > threshold` не меняется; protocol v2 занимает первые `16` bytes payload, остальной payload заполнен нулями до `1500` bytes.

### 12.3. Собрать Controller Tool На RockPI

Перенести исходники на RockPI через VisionFive:

```bash
scripts/deploy_controller_to_rockpi.sh
```

Собрать на RockPI:

```bash
scripts/build_controller_on_rockpi.sh
```

Скрипт собирает default targets и отдельный GPIO target `controller-gpio-loop`. На RockPI проверена `libgpiod` version `2.2.4`.

Эквивалентная ручная GPIO-сборка:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && make controller-gpio-loop"'
```

### 12.4. Проверить Once Exchange

Запустить одиночный request/response с RockPI:

```bash
scripts/run_controller_once_on_rockpi.sh root@10.42.0.211 root@10.43.0.2 /root/device-controller end0 4101 600 500 0 2000
```

Ожидаемый вывод:

```text
sent request seq=4101 bytes=1514 sensor=600 threshold=500 forced_output=0
received response seq=4101 output=1 status=0
```

Смысл проверки:

```text
sensor=600 > threshold=500 -> PLC output_command=1
```

В measurement profile VisionFive raw logs отключены. Проверяйте успешность exchange по выводу `controller-once` и status PLC.

Если нужно временно вернуть raw logs для диагностики, снимите `#if 0` вокруг `printf` blocks в `beremiz-project/direct-raw-plc/c_ext_0@c_ext/cfile.xml`.

Старые диагностические строки до quiet profile выглядели так:

```text
direct raw recv request seq=4101 sensor=600 threshold=500 forced_output=0
direct raw plc seq=4101 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=4101 output=1 status=0
```

### 12.5. Проверить Controller Loop Без GPIO

`controller-loop` отправляет requests по таймеру, чередуя LOW/HIGH значения датчика. Это проверяет устойчивость Ethernet request/response до подключения GPIO.

```bash
scripts/run_controller_loop_on_rockpi.sh root@10.42.0.211 root@10.43.0.2 /root/device-controller end0 4204 4 100 2000
```

Ожидаемый вывод:

```text
cycle=1 seq=4204 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=2 seq=4205 sensor=600 threshold=500 forced_output=0 output=1 status=0
cycle=3 seq=4206 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=4 seq=4207 sensor=600 threshold=500 forced_output=0 output=1 status=0
```

### 12.6. Запустить GPIO Controller Loop

`controller-gpio-loop` использует RockPI mapping из `rt-supervisor`: `/dev/gpiochip4`, input line `6`, output line `7`, оба edge. Rising edge отправляет HIGH sensor value, falling edge отправляет LOW sensor value. GPIO output устанавливается в `output` из PLC response. При send/timeout error output line `7` не меняется, чтобы Arduino/rt-tester сам зафиксировал отсутствие ожидаемого edge.

```bash
scripts/run_controller_gpio_loop_on_rockpi.sh
```

Smoke-test запуска без внешнего импульса:

```bash
scripts/run_controller_gpio_loop_on_rockpi.sh root@10.42.0.211 root@10.43.0.2 /root/device-controller end0 4301 1000 1 2
```

Ожидаемый результат smoke-test: команда штатно завершается по remote timeout, ничего не печатает и не оставляет `controller-gpio-loop` process на RockPI.

Проверить RT priority RockPI controller можно так:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller; ./controller-gpio-loop -i end0 --sequence 5301 --timeout-ms 1000 --count 1 & pid=\$!; sleep 1; ps -T -p \$pid -o pid,tid,cls,rtprio,comm; kill -TERM \$pid; wait \$pid 2>/dev/null || true"'
```

Ожидаемый class/priority для `controller-gpio-loop`: `FF 80`.

GPIO IRQ thread должен получить priority `99` через consumer `rockpi4-monitor`. Проверка:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "ps -eLo pid,tid,cls,rtprio,comm,args | grep \"[i]rq/.*rockpi4-monitor\""'
```

Ожидаемый class/priority для IRQ: `FF 99`.

Полная functional проверка требует физический импульс на RockPI input line `6`.

Важно: не запускайте `controller-once`, `controller-loop` и `controller-gpio-loop` одновременно на одном RockPI `end0`. У них один EtherType `0x1122`, поэтому два raw socket consumers могут конкурировать за response frames и давать ложные timeouts.

## 13. Частые Проблемы

### Simulator Не Отвечает

Проверьте:

```bash
python3 modbus-simulator/modbus_client.py 127.0.0.1 --port 1502 read-holding 0 3
```

Если соединение отклонено, запустите simulator.

### Runtime Не Отвечает

Перезапустите runtime:

```bash
scripts/stop_runtime_on_visionfive.sh
scripts/start_runtime_on_visionfive.sh
```

### После Sync Пропала Сборка На Плате

Это ожидаемо: `sync_to_visionfive.sh` исключает `build/`. Повторите:

```bash
scripts/build_on_visionfive.sh
scripts/deploy_run_on_visionfive_runtime.sh
```

### CLI/IDE Падает На `GetLogMessage`

Runtime должен стартовать через `scripts/start_runtime_on_visionfive.sh`, потому что этот скрипт подключает `scripts/beremiz_runtime_compat_15.py`. Extension делает runtime Beremiz `1.4` совместимым с клиентом Beremiz `1.5` на ПК.

### Direct Raw Runtime Слушает Не Тот Интерфейс

Для RockPI-схемы runtime должен быть запущен через:

```bash
scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
```

Если в log видно `direct raw receiver listening on end1`, значит запущен старый runtime path для PC-side smoke-test.

В measurement profile raw receiver startup строка отключена. Этот пункт относится к старому verbose profile; сейчас правильный interface задается командой `scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0`.

### RockPI Не Доступен По SSH

Проверьте link с VisionFive:

```bash
ssh root@10.42.0.211 'ping -c 2 10.43.0.2'
```

Если ping работает, но SSH не работает, используйте serial console:

```bash
tio -b 1500000 /dev/ttyUSB0
```

и проверьте `/root/.ssh/authorized_keys` на RockPI.
