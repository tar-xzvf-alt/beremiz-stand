# Пошаговый Запуск Стенда

Инструкция описывает только текущую supervised-схему: Beremiz runtime работает под `rt-supervisor`, а обмен с RockPI идет через raw Ethernet и shared memory.

## 1. Проверить Адреса

```text
ПК:                 10.42.0.1
VisionFive end1:    10.42.0.211
VisionFive end0:    10.43.0.1
RockPI end0:        10.43.0.2
Beremiz ERPC:       ERPC://10.42.0.211:3000
```

Быстрая проверка с ПК:

```bash
ping -c 3 10.42.0.211
ssh root@10.42.0.211 true
ssh root@10.42.0.211 'ssh root@10.43.0.2 true'
```

## 2. Подготовить `rt-supervisor`

Исходники `rt-supervisor`: https://altlinux.space/besogon1238/rt-supervisor

В этом стенде используются два режима `rt-supervisor`:

- `managed-runtime` на VisionFive: supervisor запускает Beremiz runtime через `-r`;
- `hardware-controller` на RockPI: `controller-emu` переводит GPIO edges в raw Ethernet requests.

Подробнее:

- `docs/runtime-abi.md`: shared memory/futex ABI;
- `docs/boards.md`: GPIO mappings и board names;
- `docs/altlinux-packages.md`: пакеты ALT Linux;
- `docs/beremiz-runtime.md`: Beremiz wrapper и ручные команды запуска.
- `docs/install-deploy.md`: layout установки и текущий `/root/rt-supervisor` deploy.

На платах должны быть уже собраны:

```text
VisionFive: /root/rt-supervisor/Build/src/alt-rt-supervisor
RockPI:     /root/rt-supervisor/Build/src/controller-emu
```

Также на платах должны быть установлены pinning scripts из `rt-supervisor`:

```text
VisionFive: /root/pin_visionfive_supervised.sh
RockPI:     /root/pin_rockpi_controller.sh
```

Пакеты ALT Linux для сборки `rt-supervisor` на VisionFive и RockPI:

```bash
apt-get install cmake gcc make binutils glibc-devel zlib-devel libgpiod-devel
```

Пример сборки в `/root/rt-supervisor`:

```bash
cmake -B Build -DBOARD=repkapi4
cmake --build Build
```

Для RockPI используйте board, соответствующий его конфигурации в `rt-supervisor`.

## 3. Установить Пакеты ALT Linux

На ПК `x86_64`:

```bash
su - -c 'apt-get install beremiz matiec python3 python3-module-serial python3-module-requests python3-module-prometheus_client openssh-clients tar git'
```

На VisionFive `riscv64`:

```bash
apt-get install beremiz matiec python3 openssh-clients openssh-server tar git gcc make binutils glibc-devel cmake zlib-devel libgpiod-devel kernel-image-rt
```

На RockPI `aarch64`:

```bash
apt-get install python3 openssh-clients openssh-server tar git gcc make binutils glibc-devel cmake zlib-devel libgpiod-devel kernel-image-rt
```

## 4. Остановить Старый Stack

```bash
scripts/stop_supervised_stack.sh
```

Скрипт останавливает только точные процессы `controller-emu`, `alt-rt-supervisor` и `Beremiz_service.py`.

## 5. Передать Проект На VisionFive

```bash
scripts/sync_to_visionfive.sh
```

Проект попадет в:

```text
/root/beremiz-stand
```

## 6. Собрать PLC На VisionFive

```bash
scripts/build_supervised_raw_on_visionfive.sh
```

Сборка выполняется на VisionFive, потому что runtime artifact должен быть для `riscv64`.

## 7. Загрузить PLC В Runtime Directory

Для загрузки `.so` нужен временный standalone Beremiz runtime:

```bash
scripts/start_runtime_on_visionfive.sh
scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh
scripts/install_supervised_runtime_wrapper_on_visionfive.sh
scripts/stop_runtime_on_visionfive.sh
```

После этого в `/root/beremiz-runtime/supervised-raw-plc` лежит PLC и wrapper `start_runtime.sh`, который supervisor будет запускать как child process.

## 8. Запустить Supervised Stack

Для GUI-наблюдения используйте длинный watchdog timeout:

```bash
TIMEOUT_US=30000000 scripts/start_supervised_stack.sh
```

Для чистых измерений без GUI можно использовать default timeout:

```bash
scripts/start_supervised_stack.sh
```

Скрипт запускает:

- `alt-rt-supervisor` на VisionFive;
- Beremiz runtime как child supervisor;
- `controller-emu` на RockPI;
- RT priorities и CPU affinity через pinning scripts.

Внутри он использует новые wrappers из `rt-supervisor`:

```text
/root/rt-supervisor/scripts/run_supervisor.sh
/root/rt-supervisor/scripts/run_controller.sh
```

Если нужно запустить именно supervisor вручную на VisionFive, команда такая:

```bash
/root/rt-supervisor/scripts/run_supervisor.sh \
  end0 \
  30000000 \
  /root/beremiz-runtime/supervised-raw-plc/start_runtime.sh \
  /root/rt-supervisor/Build/src/alt-rt-supervisor
```

Этот wrapper удаляет старые `/dev/shm/shmem_input` и `/dev/shm/shmem_output`, затем запускает `alt-rt-supervisor -i end0 -t 30000000 -r ...`. Для запуска всего стенда вручную дополнительно нужен controller на RockPI:

```bash
/root/rt-supervisor/scripts/run_controller.sh \
  end0 \
  /root/rt-supervisor/Build/src/controller-emu
```

Проверка:

```bash
/usr/bin/python3 scripts/check_runtime_status.py ERPC://10.42.0.211:3000
ssh root@10.42.0.211 'pgrep -af "alt-rt-supervisor|Beremiz_service.py"'
ssh root@10.42.0.211 'ssh root@10.43.0.2 "pgrep -af controller-emu"'
```

Ожидаемо:

```text
PLC Status: Started
```

## 9. Подготовить GUI Debug Build

Beremiz GUI должен иметь локальный `build/VARIABLES.csv`, совпадающий с PLC на VisionFive. После каждой remote-сборки выполните:

```bash
scripts/sync_supervised_debug_build_from_visionfive.sh
```

Проверка без GUI:

```bash
timeout 8s /usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py \
  --project-home beremiz-project/supervised-raw-plc \
  --keep connect
```

Хороший признак:

```text
Latest build matches with connected target.
Debugger ready
```

Если видите ошибку про `VARIABLES.csv` или mismatch программы, снова выполните `scripts/sync_supervised_debug_build_from_visionfive.sh`.

## 10. Открыть Beremiz GUI

```bash
beremiz beremiz-project/supervised-raw-plc
```

В GUI:

1. Подключитесь к runtime `ERPC://10.42.0.211:3000` кнопкой connect/plug.
2. Дождитесь сообщений `Latest build matches with connected target` и `Debugger ready`.
3. Не нажимайте `Build`, `Transfer`, `Upload`, если хотите только наблюдать.
4. Откройте `plc_prg` в дереве проекта.
5. Включите online/debug monitoring кнопкой debug/monitor.
6. Смотрите значения переменных рядом с ST-кодом или в watch/debug view.

## 11. Что Смотреть В GUI

Основные переменные:

| Переменная | Что показывает |
| --- | --- |
| `plc_prg.sensor_value` | входное значение от RockPI |
| `plc_prg.threshold` | порог, сейчас обычно `500` |
| `plc_prg.alarm` | результат `sensor_value > threshold` |
| `plc_prg.output_command` | команда ответа PLC |
| `plc_prg.RawOutputCommand` | команда, записанная обратно в shared memory |
| `plc_prg.request_count` | сколько новых запросов увидела PLC |
| `plc_prg.high_request_count` | сколько запросов было с `sensor=600` |
| `plc_prg.low_request_count` | сколько запросов было с `sensor=400` |
| `plc_prg.last_sequence` | номер последнего обработанного запроса |

Ожидаемое поведение:

| Состояние GPIO input | `sensor_value` | `alarm` | `output_command` |
| --- | --- | --- | --- |
| falling/low request | `400` | `FALSE` | `0` |
| rising/high request | `600` | `TRUE` | `1` |

Если `alarm` меняется, смотрите `request_count` и `last_sequence`:

- если они растут, RockPI реально получает новые GPIO edges;
- если они не растут, это не новый request, а эффект отображения/reconnect GUI.

## 12. Запустить Измерение Через rt-tester

Измеритель находится в соседнем проекте `rt-tester`:

```bash
cd /home/taranev/work_repos/rt/rt-tester/src/pc-receiver
python3 receiver.py --params measurement.conf
```

Если receiver только что подключился к Arduino, дождитесь ответа `Measurement stopped by Arduino`, затем введите `start`. Если первый старт сбился поздним `STOP`, введите `start` второй раз.

Для GUI это не обязательно: переменные можно наблюдать и без receiver, если на RockPI input приходят GPIO edges.

## 13. Остановить Стенд

```bash
scripts/stop_supervised_stack.sh
```

Если нужно остановить только временный standalone runtime:

```bash
scripts/stop_runtime_on_visionfive.sh
```

## 14. Частые Проблемы

`Не удалось открыть/прочитать VARIABLES.csv`:

```bash
scripts/sync_supervised_debug_build_from_visionfive.sh
```

`Отлаживаемая программа не соответствует программе в ПЛК`:

```bash
scripts/build_supervised_raw_on_visionfive.sh
scripts/deploy_run_supervised_raw_on_visionfive_runtime.sh
scripts/sync_supervised_debug_build_from_visionfive.sh
```

GUI подключается и быстро отваливается:

```bash
TIMEOUT_US=30000000 scripts/start_supervised_stack.sh
```

Проверить текущий timeout supervisor:

```bash
ssh root@10.42.0.211 'pgrep -af alt-rt-supervisor'
```

В аргументах должно быть `-t 30000000` или больше для GUI-сессии.
