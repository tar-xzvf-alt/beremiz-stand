# Quickstart Для Supervised RT Stand

Это короткий путь для запуска текущего стенда без знания всех внутренних
скриптов. Единая точка входа:

```bash
scripts/stand.py
```

По умолчанию используется profile:

```text
profiles/visionfive-rockpi.conf
```

## 1. Проверить Стенд

```bash
cd /home/taranev/work_repos/beremiz-stand
scripts/stand.py doctor
scripts/stand.py status
```

`doctor` проверяет локальные утилиты, SSH до VisionFive/RockPI, пути к
`rt-supervisor`, binaries, runtime wrapper, Arduino port и валидность board names.
Prometheus/Grafana в этом выводе считаются optional: они могут быть не запущены
до trace-теста.
`status` даёт короткий read-only summary текущего runtime/network состояния.

Если после сброса Ethernet-настроек ПК/VisionFive не видно, сначала выполните:

```bash
scripts/stand.py network-restore
scripts/stand.py network-check
```

`network-restore` восстанавливает локальный Ethernet profile ПК и, если
VisionFive уже доступен по SSH, закрепляет адреса VisionFive/RockPI через
NetworkManager.

После успешного `network-restore` ПК должен ходить на RockPI напрямую через
VisionFive как router:

```bash
ssh root@10.43.0.2
curl http://10.43.0.2:9201/metrics
```

Если `network-check` пишет, что VisionFive не видит RockPI, сначала проверьте
питание/линк RockPI: direct route с ПК не заработает, пока сам RockPI не отвечает
на `10.43.0.2` со стороны VisionFive.

RockPI UART в текущем стенде работает на `1500000` baud.

Проверить рассинхрон часов ПК/VisionFive/RockPI:

```bash
scripts/stand.py time-check
```

Восстановить время плат по текущим часам ПК:

```bash
scripts/stand.py time-restore
```

Большой skew объясняет предупреждения `timestamp ... in future` при `tar` и
`cmake --build`.

## 2. Обновить `rt-supervisor` На Платах

Если нужно обновить `rt-supervisor` на платах из локального checkout:

```bash
scripts/stand.py deploy-rt-supervisor
scripts/stand.py build-rt-supervisor --clean-first
```

Команды собирают нативно на VisionFive/RockPI с board names из profile.
Перед реальным обновлением можно проверить действия без записи на платы:

```bash
scripts/stand.py deploy-rt-supervisor --dry-run
scripts/stand.py build-rt-supervisor --clean-first --dry-run
```

## 3. Обновить PLC На VisionFive

Если менялся Beremiz project/runtime wrapper, обновите PLC на VisionFive:

```bash
scripts/stand.py sync-stand
scripts/stand.py build-plc
scripts/stand.py install-runtime-wrapper
scripts/stand.py start-runtime
scripts/stand.py deploy-plc
```

Для проверки без выполнения используйте `--dry-run` у каждой команды.

## 4. Полный Deploy И Logs

Полный deploy всего стенда одной командой:

```bash
scripts/stand.py deploy-all
```

Перед реальным deploy можно посмотреть последовательность:

```bash
scripts/stand.py deploy-all --dry-run
```

Сразу после проблемного запуска собрать логи:

```bash
scripts/stand.py collect-logs
```

По умолчанию logs попадут в `/tmp/rt-stand-logs-*`.

## 5. Запустить Обычный Smoke Без Trace

```bash
scripts/stand.py test-smoke
```

Переопределить количество групп:

```bash
scripts/stand.py test-smoke --groups 2
```

Переопределить частоту Arduino через период в микросекундах:

```bash
scripts/stand.py test-smoke --groups 2 --interval-us 1000
```

## 6. Запустить Trace Smoke

```bash
scripts/stand.py test-trace --groups 2
```

Эта команда сама стартует локальный trace Prometheus helper, затем запускает
smoke с `TRACE_MODE=prometheus` и импортирует trace metrics в SQLite.

Ожидаемый признак успеха для `--groups 2`:

```text
Imported trace metrics: 10
```

## 7. Открыть Grafana

```bash
scripts/stand.py grafana-start
```

Откройте:

```text
http://127.0.0.1:3001/d/rt-trace-stages
```

В dashboard выберите `session_id`, напечатанный `test-trace`.

## 8. Посмотреть Trace Summary

```bash
scripts/stand.py trace-summary
scripts/stand.py trace-summary --session-id 810963
scripts/stand.py trace-summary --all
```

По умолчанию показывает только стадии VisionFive (плата с Beremiz).
С `--all` добавляются стадии RockPI.

## 9. Частые Команды

```bash
scripts/stand.py start
scripts/stand.py status
scripts/stand.py deploy-all --dry-run
scripts/stand.py deploy-all
scripts/stand.py network-check
scripts/stand.py network-restore
scripts/stand.py time-check
scripts/stand.py deploy-rt-supervisor
scripts/stand.py build-rt-supervisor --clean-first
scripts/stand.py sync-stand
scripts/stand.py build-plc
scripts/stand.py install-runtime-wrapper
scripts/stand.py start-runtime
scripts/stand.py deploy-plc
scripts/stand.py check
scripts/stand.py stop
scripts/stand.py trace-start
scripts/stand.py trace-stop
scripts/stand.py grafana-start
scripts/stand.py grafana-stop
scripts/stand.py trace-summary
scripts/stand.py test-ab
scripts/stand.py collect-logs
```

## 10. Создать Новый Profile

Профиль описывает роли плат в стенде: какая плата играет роль supervisor
(Beremiz + `alt-rt-supervisor`), а какая — controller (`controller-emu` + GPIO).
Можно менять платы местами или подключать другие платы из поддерживаемого набора.

### Структура Профиля

Профиль — это `.conf` файл в `profiles/` с четырьмя секциями:

```ini
[pc]           # ПК: пути к проектам, сеть, Arduino
[supervisor]   # Плата с Beremiz runtime и alt-rt-supervisor
[controller]   # Плата с controller-emu и GPIO
[measurement]  # Параметры измерений
```

### Секция `[pc]` — Локальный ПК

| Ключ | Описание | Пример |
|------|----------|--------|
| `rt_tester_dir` | Путь к `rt-tester` | `/home/user/work_repos/rt/rt-tester` |
| `rt_supervisor_dir` | Путь к `rt-supervisor` (для deploy) | `/home/user/work_repos/rt/rt-supervisor` |
| `arduino_port` | Последовательный порт Arduino | `/dev/ttyACM0` |
| `ethernet_iface` | Ethernet-интерфейс ПК, подключённый к стенду | `enp2s0` |
| `ethernet_connection` | Имя NetworkManager-подключения | `Проводное подключение 1` |
| `ethernet_addr` | Адрес ПК в сети стенда | `10.42.0.1/24` |
| `controller_route` | Подсеть, в которой находится controller | `10.43.0.0/24` |
| `controller_gateway` | Шлюз к controller (IP платы с forwarding) | `10.42.0.211` |
| `ssh_public_key` | Публичный SSH-ключ для установки на controller | `/home/user/.ssh/id_ed25519.pub` |
| `trace_prometheus_url` | URL локального trace Prometheus | `http://127.0.0.1:9091` |
| `trace_prometheus_addr` | Адрес локального trace Prometheus | `127.0.0.1:9091` |
| `trace_grafana_addr` | Адрес локальной Grafana | `127.0.0.1:3001` |

### Секция `[supervisor]` — Плата с Beremiz

| Ключ | Описание | Пример |
|------|----------|--------|
| `ssh` | SSH-строка для подключения | `root@10.42.0.211` |
| `label` | Отображаемое имя | `VisionFive` |
| `board` | Имя платы для сборки `-DBOARD=` (см. таблицу) | `repkapi4` |
| `iface` | Интерфейс для raw Ethernet | `end0` |
| `pc_iface` | Интерфейс, смотрящий в сторону ПК | `end1` |
| `pc_connection` | Имя NetworkManager-подключения на `pc_iface` | `end1` |
| `pc_addr` | Адрес на `pc_iface` | `10.42.0.211/24` |
| `controller_iface` | Интерфейс, смотрящий в сторону controller | `end0` |
| `controller_connection` | Имя NetworkManager-подключения на `controller_iface` | `end0-static` |
| `controller_addr` | Адрес на `controller_iface` | `10.43.0.1/24` |
| `enable_ip_forward` | Включить IPv4 forwarding (если плата — роутер) | `yes` или `no` |
| `rt_supervisor_dir` | Путь к `rt-supervisor` на плате | `/root/rt-supervisor` |
| `beremiz_stand_dir` | Путь к `beremiz-stand` на плате | `/root/beremiz-stand` |
| `plc_project` | Имя Beremiz-проекта (относительно `beremiz_stand_dir`) | `beremiz-project/supervised-raw-plc` |
| `runtime_dir` | Директория Beremiz runtime | `/root/beremiz-runtime/supervised-raw-plc` |
| `runtime_bind_ip` | IP для ERPC | `10.42.0.211` |
| `runtime_port` | Порт ERPC | `3000` |
| `supervisor_bin` | Путь к `alt-rt-supervisor` на плате | `/root/rt-supervisor/Build/src/alt-rt-supervisor` |
| `runtime_wrapper` | Путь к `start_runtime.sh` на плате | `/root/beremiz-runtime/supervised-raw-plc/start_runtime.sh` |
| `erpc_url` | ERPC URI для проверки статуса | `ERPC://10.42.0.211:3000` |
| `pinning_script` | Путь к скрипту RT-pinning для supervisor | `/root/pin_visionfive_supervised.sh` |

### Секция `[controller]` — Плата с GPIO

| Ключ | Описание | Пример |
|------|----------|--------|
| `ssh` | SSH-строка для подключения | `root@10.43.0.2` |
| `ssh_jump` | SSH-jump хост (если controller не доступен с ПК напрямую). Укажите тот же `ssh`, если доступен напрямую | `root@10.42.0.211` |
| `label` | Отображаемое имя | `RockPI` |
| `board` | Имя платы для сборки `-DBOARD=` (см. таблицу) | `rockpi4` |
| `iface` | Интерфейс для raw Ethernet | `end0` |
| `connection` | Имя NetworkManager-подключения | `end0-static` |
| `addr` | Адрес на `iface` | `10.43.0.2/24` |
| `pc_route` | Маршрут от controller обратно к ПК | `10.42.0.0/24` |
| `pc_gateway` | Шлюз от controller к ПК | `10.43.0.1` |
| `uart` | UART-устройство на ПК для доступа к controller | `/dev/ttyUSB0` |
| `uart_baud` | Baud rate UART | `1500000` |
| `rt_supervisor_dir` | Путь к `rt-supervisor` на плате | `/root/rt-supervisor` |
| `controller_bin` | Путь к `controller-emu` на плате | `/root/rt-supervisor/Build/src/controller-emu` |
| `pinning_script` | Путь к скрипту RT-pinning для controller | `/root/pin_rockpi_controller.sh` |

### Секция `[measurement]` — Параметры измерений

| Ключ | Описание | Пример |
|------|----------|--------|
| `params` | Путь к конфигурации `rt-tester` receiver | `.../measurement-supervised-smoke.conf` |
| `groups` | Групп по умолчанию | `2` |
| `measurements_per_group` | Измерений в группе | `1500` |
| `interval_us` | Интервал Arduino (мкс) | `5000` |
| `receiver_timeout_sec` | Таймаут receiver | `120` |

### Таблица Board Names

Board name из `gpio_config.h`. Используется для сборки `controller-emu`
(флаг `-DBOARD=`) и в pinning-скриптах:

| Board name | GPIO chip | In/Out offset | Consumer name |
|------------|-----------|---------------|---------------|
| `bcvm` | `/dev/gpiochip0` | 15 / 9 | `bcvm-monitor` |
| `bvc` | `/dev/gpiochip0` | 0 / 4 | `bvcarm-mo` |
| `bvc_arm` | `/dev/gpiochip0` | 0 / 4 | `bvcarm-mo` |
| `lichee` | `/dev/gpiochip0` | 140 / 144 | `lichee-monitor` |
| `radxa` | `/dev/gpiochip3` | 10 / 11 | `radxa-monitor` |
| `starfive` | `/dev/gpiochip0` | 60 / 61 | `starfive-monitor` |
| `mangopi` | `/dev/gpiochip0` | 35 / 36 | `mangopi-monitor` |
| `rockpi4` | `/dev/gpiochip4` | 6 / 7 | `rockpi4-monitor` |
| `repkapi4` | `/dev/gpiochip1` | 205 / 204 | `repkapi4-monitor` |

### Сетевые Топологии

**С拓扑 1: supervisor — роутер, controller за ним**

```
ПК 10.42.0.1 ↔ supervisor (end1 10.42.0.211, end0 10.43.0.1) ↔ controller (end0 10.43.0.2)
```

- `[supervisor] enable_ip_forward = yes`
- `[pc] controller_gateway = 10.42.0.211` (supervisor)
- `[controller] ssh_jump = root@10.42.0.211` (через supervisor)
- `[controller] pc_gateway = 10.43.0.1` (обратно через supervisor)
- Пример: `visionfive-rockpi.conf`

**Топология 2: supervisor напрямую, controller — роутер**

```
ПК 10.42.0.1 ↔ controller (end1 10.42.0.211, end0 10.43.0.1) ↔ supervisor (end0 10.43.0.2)
```

- `[controller] enable_ip_forward = yes` (добавить в секцию)
- `[pc] controller_gateway = 10.42.0.211` (controller)
- `[supervisor]` — доступен через маршрут ПК `10.43.0.0/24 via 10.42.0.211`
- `[controller] ssh_jump = root@10.42.0.211` (или такой же как `ssh`, если доступен напрямую)
- Пример: `rockpi-visionfive.conf` (с `ssh_jump = ssh`)

### Пример Создания Профиля

Допустим, нужно сделать StarFive (`starfive`) supervisor, а RockPI (`rockpi4`)
controller. Копируем существующий профиль:

```bash
cp profiles/visionfive-rockpi.conf profiles/starfive-rockpi.conf
```

Меняем:

```ini
[supervisor]
ssh = root@10.42.0.100      # IP StarFive
label = StarFive
board = starfive             # Board name из таблицы
pc_iface = end1
pc_addr = 10.42.0.100/24
controller_addr = 10.43.0.1/24
enable_ip_forward = yes      # StarFive — роутер
runtime_bind_ip = 10.42.0.100
erpc_url = ERPC://10.42.0.100:3000
pinning_script = /root/pin_starfive_supervised.sh

[controller]
ssh = root@10.43.0.2
ssh_jump = root@10.42.0.100  # через StarFive
label = RockPI
board = rockpi4
addr = 10.43.0.2/24
pc_gateway = 10.43.0.1       # обратно через StarFive
pinning_script = /root/pin_rockpi_controller.sh
```

Проверяем:

```bash
scripts/stand.py --profile profiles/starfive-rockpi.conf doctor
scripts/stand.py --profile profiles/starfive-rockpi.conf network-check
scripts/stand.py --profile profiles/starfive-rockpi.conf status
```

### Что Нужно Для Новой Комбинации Плат

1. **Profile** (`.conf`) — создать по шаблону
2. **Pinning scripts** для обеих ролей:
   - Supervisor: `/root/pin_<board>_supervised.sh` — приоритеты `alt-rt-supervisor`, Beremiz, NIC IRQ
   - Controller: `/root/pin_<board>_controller.sh` — приоритеты `controller-emu`, GPIO IRQ, NIC IRQ
   - Если готовых нет — скопировать из `rt-supervisor/scripts/pin_*` и поправить consumer name, CPU layout, IRQ-паттерны
3. **Beremiz** на supervisor-плате (`apt-get install beremiz matiec`)
4. **cmake/gcc/libgpiod** на обеих платах (`apt-get install cmake gcc libgpiod-devel`)
5. **Пакеты на ПК** — `python3`, `ssh`, `scp`, `tar` (см. `doctor`)
6. **Arduino** — подключен к GPIO-пинам controller-платы согласно `board` из таблицы

### Проверка Нового Профиля

```bash
# 1. Сеть и доступ
scripts/stand.py --profile profiles/my-stand.conf doctor
scripts/stand.py --profile profiles/my-stand.conf network-check

# 2. Время
scripts/stand.py --profile profiles/my-stand.conf time-restore

# 3. Deploy и сборка
scripts/stand.py --profile profiles/my-stand.conf deploy-rt-supervisor
scripts/stand.py --profile profiles/my-stand.conf build-rt-supervisor --clean-first

# 4. PLC (только на supervisor)
scripts/stand.py --profile profiles/my-stand.conf sync-stand
scripts/stand.py --profile profiles/my-stand.conf build-plc
scripts/stand.py --profile profiles/my-stand.conf install-runtime-wrapper
scripts/stand.py --profile profiles/my-stand.conf start-runtime
scripts/stand.py --profile profiles/my-stand.conf deploy-plc

# 5. Smoke test
scripts/stand.py --profile profiles/my-stand.conf test-trace --groups 2
```

## 11. Остановить Все После Тестов

```bash
scripts/stand.py stop
scripts/stand.py trace-stop
scripts/stand.py grafana-stop
```

## Shell Scripts

Все shell-скрипты в `scripts/` теперь являются compatibility wrappers,
передающими вызов в `scripts/stand.py`. Полная логика стенда находится
в Python внутри `stand.py`.
