# RockPI Controller Plan

Этот документ фиксирует следующий этап стенда: вынести генерацию raw Ethernet packets с ПК на отдельное устройство RockPI и приблизить архитектуру к `rt-supervisor/controller-emu`.

## Текущая База

Уже работает ветка `experiment/raw-ethernet-plc`:

- `beremiz-project/direct-raw-plc` запускается на VisionFive 2.
- Beremiz `c_ext` внутри runtime принимает raw Ethernet frames с EtherType `0x1122`.
- PLC получает значения напрямую через external variables, без Modbus simulator.
- `device-controller/controller-once` проверяет цепочку `RockPI end0 -> VisionFive end0 -> Beremiz PLC -> raw Ethernet response -> RockPI end0`.
- `device-controller/controller-loop` проверяет cyclic request/response без GPIO.
- `device-controller/controller-gpio-loop` добавлен для GPIO edge-driven цикла на RockPI.
- `scripts/demo_direct_raw_ethernet.py` оставлен как PC-side smoke-test direct raw path без RockPI.

ПК уже убран из raw Ethernet control loop: он используется для SSH/ERPC/monitoring через VisionFive `end1`.

## Целевая Топология

```text
PC <-> VisionFive end1
  SSH / Beremiz ERPC / engineering / monitoring

RockPI <-> VisionFive end0
  raw Ethernet request/response control traffic

GPIO source -> RockPI input GPIO
RockPI output GPIO -> external receiver / Arduino / meter
```

Роли:

- VisionFive 2 остается главным PLC-контроллером.
- `end1` на VisionFive остается для связи с ПК и не участвует в real-time control loop.
- `end0` на VisionFive выделяется под point-to-point raw Ethernet link с RockPI.
- RockPI становится внешним устройством/controller-emulator: GPIO event инициирует raw Ethernet request, response от PLC управляет GPIO output.
- ПК используется только для разработки, загрузки, мониторинга и диагностики.

## Почему Начинаем Без GPIO

Сначала нужно проверить сетевой request/response отдельно от железных ног:

```text
RockPI controller-once
  send one raw Ethernet request
        |
        v
VisionFive direct-raw-plc
  receive request
  run PLC logic
  send raw Ethernet response
        |
        v
RockPI controller-once
  print output/status
```

Это разделяет два класса ошибок:

- raw Ethernet protocol / interface / MAC / response timeout;
- GPIO chip / line offsets / edge detection / output polarity.

## Protocol Direction

Текущий MVP payload version `1`:

```text
magic=BETH, version=1, sequence, sensor, threshold, forced_output
```

Для bidirectional обмена нужен version `2` с типом сообщения:

| Field | Type | Request Meaning | Response Meaning |
| --- | --- | --- | --- |
| `magic` | `4s` | `BETH` | `BETH` |
| `version` | `u8` | `2` | `2` |
| `msg_type` | `u8` | `1=request` | `2=response` |
| `sequence` | `u32` | request id | echoed request id |
| `value0` | `u16` | `sensor_value` | `output_command` |
| `value1` | `u16` | `threshold` | `status` |
| `value2` | `u16` | `forced_output` | reserved |

Минимальные правила:

- response должен повторять `sequence` request;
- RockPI должен игнорировать response с чужим `sequence`;
- VisionFive должен отправлять response на source MAC request;
- timeout на RockPI обязателен;
- при timeout GPIO output остается без изменения, чтобы Arduino/rt-tester зафиксировал отсутствие ожидаемого edge.

Measurement packet size profile:

```text
one raw Ethernet request frame per GPIO edge
one raw Ethernet response frame per PLC answer
frame size: 1514 bytes total
payload size: 1500 bytes
protocol v2 fields: first 16 payload bytes
padding: zero-filled
```

Это intentionally не повторяет полный `rt-supervisor` logical message `96 KiB`; fragmentation/reassembly не включены, чтобы измерять влияние размера одного Ethernet frame при прежней PLC threshold logic.

## Этапы Работы

### Этап 1. Документированный Checkpoint

- Зафиксировать этот roadmap отдельным commit.
- Сохранить рабочее состояние перед изменением протокола и runtime.

### Этап 2. Bidirectional Once Exchange Без GPIO

VisionFive:

- Настроить direct raw runtime на interface `end0` через `RAW_ETH_INTERFACE=end0`.
- Расширить `c_ext` приемником protocol v2 request.
- Запоминать source MAC последнего request.
- После вычисления `RawOutputCommand` отправлять raw Ethernet response обратно на source MAC.
- Логировать request и response:

```text
direct raw recv request seq=... sensor=... threshold=... forced_output=...
direct raw send response seq=... output=... status=0
```

RockPI / временно PC для smoke-test:

- Добавить `device-controller/controller-once`.
- Команда должна выглядеть примерно так:

```bash
./controller-once -i eth0 --sensor 600 --threshold 500 --forced-output 0
```

Ожидаемый результат:

```text
sent request seq=...
received response seq=... output=1 status=0
```

Первый smoke-test выполнен с ПК вместо RockPI на существующем линке `PC enp2s0 <-> VisionFive end1`, пока физический линк `RockPI <-> VisionFive end0` еще не настроен.

Команда:

```bash
sudo ./device-controller/controller-once -i enp2s0 --sequence 1001 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000
```

Вывод `controller-once`:

```text
sent request seq=1001 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=1001 output=1 status=0
```

Runtime log на VisionFive:

```text
direct raw recv request seq=1001 sensor=600 threshold=500 forced_output=0
direct raw plc seq=1001 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=1001 output=1 status=0
```

Это подтверждает protocol v2 `request -> PLC -> response` без GPIO на временном PC sender link.

Также проверен retry/duplicate сценарий: два одинаковых request с одним `sequence` должны получать два response. Это нужно, чтобы controller мог повторить request после локального timeout или потери response.

Команды:

```bash
sudo ./device-controller/controller-once -i enp2s0 --sequence 1003 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000
sudo ./device-controller/controller-once -i enp2s0 --sequence 1003 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000
```

Вывод:

```text
sent request seq=1003 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=1003 output=1 status=0
sent request seq=1003 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=1003 output=1 status=0
```

Runtime log:

```text
direct raw recv request seq=1003 sensor=600 threshold=500 forced_output=0
direct raw plc seq=1003 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=1003 output=1 status=0
direct raw recv request seq=1003 sensor=600 threshold=500 forced_output=0
direct raw send response seq=1003 output=1 status=0
```

### Этап 2.1. RockPI Once Exchange Через VisionFive `end0`

Фактически поднят целевой Ethernet link:

```text
PC <-> VisionFive end1
  10.42.0.211/24, SSH/ERPC остаются без изменений

RockPI end0 <-> VisionFive end0
  VisionFive end0: 10.43.0.1/24
  RockPI end0:     10.43.0.2/24
```

RockPI console доступна через serial:

```bash
tio -b 1500000 /dev/ttyUSB0
```

Для non-interactive bring-up использовался прямой serial write/read через `/dev/ttyUSB0`; RockPI уже имел root shell. RockPI параметры:

```text
arch: aarch64
kernel: 6.12.90-rt-alt1
ethernet interface: end0
RockPI end0 MAC: b6:1e:73:23:c5:45
compiler: /bin/cc
```

VisionFive `end0` настраивается helper script:

```bash
./scripts/configure_rockpi_link_on_visionfive.sh
```

Direct raw runtime запускается на VisionFive с receiver на `end0`:

```bash
./scripts/stop_runtime_on_visionfive.sh root@10.42.0.211 /root/beremiz-runtime/direct-raw-plc
./scripts/start_direct_raw_runtime_on_visionfive.sh root@10.42.0.211 end0
./scripts/deploy_run_direct_raw_on_visionfive_runtime.sh
```

`controller-once` был перенесен на RockPI и собран там:

```bash
ssh root@10.42.0.211 'scp -r /root/beremiz-stand/device-controller root@10.43.0.2:/root/device-controller'
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && make clean && make"'
```

Проверенный once exchange с RockPI:

```bash
ssh root@10.42.0.211 'ssh root@10.43.0.2 "cd /root/device-controller && ./controller-once -i end0 --sequence 2001 --sensor 600 --threshold 500 --forced-output 0 --timeout-ms 2000"'
```

Вывод RockPI:

```text
sent request seq=2001 bytes=30 sensor=600 threshold=500 forced_output=0
received response seq=2001 output=1 status=0
```

Runtime log на VisionFive:

```text
direct raw receiver listening on end0, EtherType=0x1122
direct raw recv request seq=2001 sensor=600 threshold=500 forced_output=0
direct raw plc seq=2001 sensor=600 threshold=500 forced_output=0 output=1
direct raw send response seq=2001 output=1 status=0
```

Проверен duplicate/retry на целевом RockPI link:

```text
sent request seq=2002 bytes=30 sensor=400 threshold=500 forced_output=1
received response seq=2002 output=0 status=0
sent request seq=2002 bytes=30 sensor=400 threshold=500 forced_output=1
received response seq=2002 output=0 status=0
```

Это завершает первый сетевой этап: `RockPI end0 -> VisionFive end0 -> Beremiz PLC -> raw Ethernet response -> RockPI end0`, пока без GPIO.

### Этап 3. RockPI Deploy Path

Добавлены scripts:

```text
scripts/deploy_controller_to_rockpi.sh
scripts/build_controller_on_rockpi.sh
scripts/run_controller_once_on_rockpi.sh
scripts/run_controller_loop_on_rockpi.sh
scripts/run_controller_gpio_loop_on_rockpi.sh
```

Нужные параметры:

- SSH user/host RockPI;
- Ethernet interface RockPI;
- способ настройки link `RockPI <-> VisionFive end0`;
- наличие compiler/libgpiod;
- путь установки бинарника.

Проверенный deploy/build flow:

```bash
scripts/deploy_controller_to_rockpi.sh
scripts/build_controller_on_rockpi.sh
```

`deploy_controller_to_rockpi.sh` переносит archive через VisionFive и нормализует timestamps на RockPI, чтобы `make` не предупреждал о clock skew.

### Этап 4. Controller Loop Без GPIO

Добавлен режим, который отправляет requests в цикле по таймеру:

```bash
./controller-loop -i end0 --period-ms 1000
```

Цель:

- проверить устойчивость request/response;
- проверить sequence handling;
- проверить timeout и reconnect behavior;
- убедиться, что ПК не участвует в control loop.

Проверенный запуск на RockPI:

```bash
scripts/run_controller_loop_on_rockpi.sh root@10.42.0.211 root@10.43.0.2 /root/device-controller end0 4204 4 100 2000
```

Результат:

```text
cycle=1 seq=4204 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=2 seq=4205 sensor=600 threshold=500 forced_output=0 output=1 status=0
cycle=3 seq=4206 sensor=400 threshold=500 forced_output=1 output=0 status=0
cycle=4 seq=4207 sensor=600 threshold=500 forced_output=0 output=1 status=0
```

Это завершает сетевой cyclic этап без GPIO. Следующий этап: заменить timer-driven cycle на GPIO edge-driven cycle.

### Этап 5. GPIO Loop На RockPI

Использовать RockPI mapping из `rt-supervisor/src/gpio_config.h`:

```c
GPIO_CHIP     "/dev/gpiochip4"
GPIO_LINE_IN  6
GPIO_LINE_OUT 7
GPIO_EDGE     both
```

Добавлен `controller-gpio-loop`. Default mapping:

```text
/dev/gpiochip4 input=6 output=7
```

Цикл:

```text
wait GPIO edge
  -> rising edge: sensor=600, forced_output=0
  -> falling edge: sensor=400, forced_output=1
  -> send raw request seq=N
  -> wait raw response seq=N
  -> set GPIO output to response output_command
```

Требования:

- timeout обязателен;
- на timeout/send error output line `7` остается без изменения, чтобы Arduino/rt-tester зафиксировал отсутствие ожидаемого edge;
- для measurement profile per-cycle logging отключен;
- не зависеть от ПК во время работы.

RT measurement profile:

```text
direct-raw-plc task period: T#10ms
VisionFive raw receiver thread: SCHED_FIFO priority 80
VisionFive PLC task thread: SCHED_FIFO priority 85
RockPI controller-gpio-loop: SCHED_FIFO priority 80
RockPI GPIO IRQ thread: SCHED_FIFO priority 99
mlockall(MCL_CURRENT | MCL_FUTURE): enabled on both devices
```

Supervised raw measurement profile differs from direct raw: Beremiz PLC cyclic thread uses `SCHED_FIFO 92`, `alt-rt-supervisor` uses `SCHED_FIFO 88`, RockPI `controller-emu` uses `SCHED_FIFO 85`, Ethernet IRQs are raised to `82` on VisionFive and `75` on RockPI, and `node_exporter` remains `TS` on housekeeping CPUs.

Build на RockPI:

```bash
scripts/build_controller_on_rockpi.sh
```

Проверено на RockPI:

```text
libgpiod: 2.2.4
gpiochip4 lines 6/7: free before run
make controller-gpio-loop: success
```

Smoke-test запуска без внешнего импульса:

```bash
scripts/run_controller_gpio_loop_on_rockpi.sh root@10.42.0.211 root@10.43.0.2 /root/device-controller end0 4301 1000 1 2
```

Результат в quiet profile: команда завершается по remote timeout без штатного вывода и не оставляет `controller-gpio-loop` process.

До quiet profile startup строка выглядела так:

```text
controller-gpio-loop started iface=end0 gpio=/dev/gpiochip4 input=6 output=7
```

Functional test не завершен: нужен физический edge на RockPI input line `6`.

Важно: `controller-once`, `controller-loop` и `controller-gpio-loop` нельзя запускать параллельно на одном RockPI `end0`, так как они конкурируют за raw Ethernet response frames одного EtherType `0x1122`.

### Этап 6. Monitoring / Demo

ПК должен использоваться только как engineering/monitoring station:

- SSH на VisionFive через `end1`;
- Beremiz ERPC monitoring через `end1`;
- runtime logs;
- опционально packet capture на `end0`;
- инструкции запуска полного стенда.

Минимальный успешный demo:

```text
1. PC запускает/мониторит VisionFive runtime.
2. RockPI запускает controller GPIO loop.
3. GPIO input на RockPI меняется.
4. RockPI отправляет request на VisionFive end0.
5. VisionFive PLC считает output.
6. VisionFive отправляет response.
7. RockPI меняет GPIO output.
8. PC видит PLC variables/logs, но не участвует в loop.
```

### Этап 7. Shared Memory / Supervisor Variant

После работающего direct raw GPIO loop выбран вариант максимального переиспользования `rt-supervisor` как есть:

```text
RockPI rt-supervisor/controller-emu
        |
        v
VisionFive alt-rt-supervisor
  raw socket / watchdog / timeout / RT priority
  shared memory input/output
        |
        v
Beremiz runtime supervised-raw-plc c_ext
  __retrieve reads shm -> PLC variables
  __publish writes PLC outputs -> shm
```

Плюсы этого этапа:

- raw Ethernet code уходит из Beremiz runtime;
- supervisor может иметь отдельные RT priorities и watchdog;
- Beremiz `__retrieve`/`__publish` остаются быстрым copy path;
- архитектура становится штатным `rt-supervisor` path для transport/restart;
- измеряется не single-frame direct raw path, а 96 KiB logical payload с fragmentation/reassembly.

Protocol v2 `BETH` остается в первых `16` bytes payload. В direct raw path это первые `16` bytes Ethernet payload, а в supervised path это первые `16` bytes `controller_msg_t.payload` размером `96 KiB`.

Добавлен отдельный Beremiz project:

```text
beremiz-project/supervised-raw-plc
```

Добавлены helper scripts:

```text
scripts/build_supervised_raw_on_visionfive.sh
scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh
scripts/install_supervised_runtime_wrapper_on_visionfive.sh
```

Wrapper установлен на VisionFive как:

```text
/root/beremiz-runtime/supervised-raw-plc/start_runtime.sh
```

Smoke-test `alt-rt-supervisor -r start_runtime.sh` уже подтвердил, что Beremiz runtime стартует как child supervisor и создаются `/dev/shm/shmem_input`/`shmem_output` размером `98312` bytes.

## Открытые Вопросы

Перед deploy на RockPI нужно уточнить:

- точная электрическая схема GPIO input/output;
- нужна ли инверсия polarity для конкретной проводки.

## Ближайший Следующий Шаг

После `controller-gpio-loop` следующий практический шаг:

```text
Подать физический edge на RockPI input line 6 и проверить, что output line 7 повторяет PLC response output.
```
