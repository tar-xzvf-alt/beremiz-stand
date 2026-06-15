# RockPI Controller Plan

Этот документ фиксирует следующий этап стенда: вынести генерацию raw Ethernet packets с ПК на отдельное устройство RockPI и приблизить архитектуру к `rt-supervisor/controller-emu`.

## Текущая База

Уже работает ветка `experiment/raw-ethernet-plc`:

- `beremiz-project/direct-raw-plc` запускается на VisionFive 2.
- Beremiz `c_ext` внутри runtime принимает raw Ethernet frames с EtherType `0x1122`.
- PLC получает значения напрямую через external variables, без Modbus simulator.
- `scripts/demo_direct_raw_ethernet.py` проверяет цепочку `PC raw sender -> VisionFive Beremiz runtime -> PLC logic`.

Текущий demo все еще использует ПК как отправитель raw Ethernet packets. Следующий этап должен убрать ПК из control loop.

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
- при timeout GPIO output должен переходить в безопасное состояние на этапе GPIO loop.

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

### Этап 3. RockPI Deploy Path

После уточнения параметров RockPI добавить scripts:

```text
scripts/build_controller_on_rockpi.sh
scripts/deploy_controller_to_rockpi.sh
```

Нужные параметры:

- SSH user/host RockPI;
- Ethernet interface RockPI;
- способ настройки link `RockPI <-> VisionFive end0`;
- наличие compiler/libgpiod;
- путь установки бинарника.

### Этап 4. Controller Loop Без GPIO

Добавить режим, который отправляет requests в цикле по таймеру или stdin:

```bash
./controller-loop -i eth0 --period-ms 1000
```

Цель:

- проверить устойчивость request/response;
- проверить sequence handling;
- проверить timeout и reconnect behavior;
- убедиться, что ПК не участвует в control loop.

### Этап 5. GPIO Loop На RockPI

Использовать RockPI mapping из `rt-supervisor/src/gpio_config.h`:

```c
GPIO_CHIP     "/dev/gpiochip4"
GPIO_LINE_IN  6
GPIO_LINE_OUT 7
GPIO_EDGE     both
```

Цикл:

```text
wait GPIO edge
  -> send raw request seq=N
  -> wait raw response seq=N
  -> set/toggle GPIO output from response output_command
```

Требования:

- timeout обязателен;
- на timeout output должен перейти в safe state;
- логировать latency по этапам: GPIO edge, Ethernet send, Ethernet receive, GPIO output;
- не зависеть от ПК во время работы.

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

После работающего GPIO loop можно приблизиться к `rt-supervisor` глубже:

```text
RockPI raw Ethernet
        |
        v
VisionFive supervisor process
  raw socket / watchdog / timeout / RT priority
  shared memory input/output
        |
        v
Beremiz runtime c_ext
  __retrieve reads shm -> PLC variables
  __publish writes PLC outputs -> shm
```

Плюсы этого этапа:

- raw Ethernet code уходит из Beremiz runtime;
- supervisor может иметь отдельные RT priorities и watchdog;
- Beremiz `__retrieve`/`__publish` остаются быстрым copy path;
- архитектура становится ближе к `rt-supervisor`.

Этот этап не делаем до завершения once exchange и GPIO loop.

## Открытые Вопросы

Перед deploy на RockPI нужно уточнить:

- SSH адрес и пользователь RockPI;
- имя Ethernet interface RockPI;
- нужна ли IP-сеть на линке `VisionFive end0 <-> RockPI` для SSH/diagnostics;
- установлен ли compiler на RockPI;
- версия libgpiod на RockPI;
- точная электрическая схема GPIO input/output;
- output должен держать состояние `0/1` или делать короткий pulse.

## Ближайший Следующий Шаг

После commit этого документа следующий кодовый шаг:

```text
Implement protocol v2 request/response in VisionFive direct-raw-plc and add a controller-once raw Ethernet tool.
```
