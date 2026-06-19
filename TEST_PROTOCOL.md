# Протокол Измерений Supervised Raw Ethernet

Этот протокол проверяет supervised-схему Beremiz runtime + `rt-supervisor` +
RockPI controller и оценивает overhead trace-сбора.

## Что Измеряем

Основная метрика берется с Arduino через `rt-tester`: latency одного GPIO
цикла от импульса до ответа.

Trace-метрики опциональны и разбивают путь на агрегированные стадии:

| Host | Stage |
| --- | --- |
| RockPI | `gpio_to_send` |
| RockPI | `request_send` |
| RockPI | `response_recv` |
| RockPI | `response_to_gpio` |
| VisionFive | `ethernet_recv` |
| VisionFive | `shmem_input` |
| VisionFive | `runtime_wait` |
| VisionFive | `shmem_output` |
| VisionFive | `ethernet_send` |

Не вычитайте timestamps между RockPI и VisionFive: clocks разные. Сравнивайте
только durations внутри одного host.

## Предусловия

На ПК:

```bash
cd /home/taranev/work_repos/beremiz-stand
```

Проверить доступность плат:

```bash
ping -c 3 10.42.0.211
ssh root@10.42.0.211 true
ssh root@10.42.0.211 'ssh root@10.43.0.2 true'
```

На платах должны быть штатные binaries:

```text
VisionFive: /root/rt-supervisor/Build/src/alt-rt-supervisor
RockPI:     /root/rt-supervisor/Build/src/controller-emu
```

Arduino должен быть подключен к ПК как `/dev/ttyACM0`. Если порт другой:

```bash
ARDUINO_PORT=/dev/ttyACM1 scripts/run_supervised_smoke.sh
```

## Быстрая Sanity-Проверка

Запустить стенд без trace и сделать короткий smoke:

```bash
TRACE_MODE=off SMOKE_GROUPS=2 scripts/run_supervised_smoke.sh
```

Ожидаемые признаки успеха:

```text
PLC Status: Started
trace_mode=off
groups=2
latencies=150
```

Если `measurement-supervised-smoke.conf` настроен на 1500 измерений в группе,
то для `SMOKE_GROUPS=2` Arduino выполнит 3000 физических измерений, а receiver
сохранит 150 worst latency samples: 75 на группу.

## Trace Через Локальный Prometheus

Если ПК не имеет прямого маршрута к `10.43.0.0/24`, используйте локальные SSH
tunnels и отдельный Prometheus на `127.0.0.1:9091`:

```bash
scripts/start_trace_prometheus_local.sh
```

Проверить trace smoke с импортом в SQLite:

```bash
TRACE_MODE=prometheus \
TRACE_PROMETHEUS_URL=http://127.0.0.1:9091 \
SMOKE_GROUPS=2 \
  scripts/run_supervised_smoke.sh
```

Ожидаемые признаки успеха:

```text
trace_mode=prometheus
Imported trace metrics: 18
trace=rockpi/gpio_to_send: groups=2 ...
trace=visionfive/runtime_wait: groups=2 ...
```

Для 2 групп ожидается 18 imported trace records: 2 groups * (4 RockPI stages +
5 VisionFive stages).

Остановить локальный Prometheus и tunnels:

```bash
scripts/stop_trace_prometheus_local.sh
```

## Trace В Grafana

Для локального просмотра trace и Arduino latency через Grafana используйте
provisioned dashboard из `rt-tester/grafana`:

```bash
scripts/start_trace_prometheus_local.sh
scripts/start_trace_grafana_local.sh
```

Затем запустите trace smoke:

```bash
TRACE_MODE=prometheus \
TRACE_PROMETHEUS_URL=http://127.0.0.1:9091 \
SMOKE_GROUPS=2 \
  scripts/run_supervised_smoke.sh
```

Откройте:

```text
http://127.0.0.1:3001/d/rt-trace-stages
```

Dashboard `RT Trace Stage Breakdown` содержит четыре панели:

- `Average Latency`
- `Maximum Latency`
- `Average Trace Stage Duration`
- `Maximum Trace Stage Duration`

Выберите `session_id`, напечатанный smoke script. Для `SMOKE_GROUPS=2` после
добавления `shmem_output` ожидается `Imported trace metrics: 18`.

Остановить Grafana:

```bash
scripts/stop_trace_grafana_local.sh
```

## A/B Overhead-Серия

Перед серией включите локальный trace Prometheus:

```bash
scripts/start_trace_prometheus_local.sh
```

Запустить короткую A/B серию:

```bash
AB_GROUPS=2 AB_REPEATS=1 scripts/run_supervised_ab_overhead.sh
```

Скрипт последовательно запускает:

| Mode | Что включено |
| --- | --- |
| `off` | только supervised stack и receiver, trace полностью выключен |
| `jsonl` | trace JSONL на платах, exporters и Prometheus выключены |
| `prometheus` | trace JSONL, exporters, Prometheus scrape и импорт в SQLite |

Для более устойчивой оценки используйте минимум 5 повторов:

```bash
AB_GROUPS=10 AB_REPEATS=5 scripts/run_supervised_ab_overhead.sh
```

Результаты сохраняются в `/tmp/rt-supervised-ab-YYYYMMDD-HHMMSS/`. В конце
печатается summary по каждому run:

```text
1-off: trace_mode=off; session=...; groups=...; latencies=...; latency_min_avg_max_us=...
1-jsonl: trace_mode=jsonl; session=...; groups=...; latencies=...; latency_min_avg_max_us=...
1-prometheus: trace_mode=prometheus; session=...; groups=...; latencies=...; latency_min_avg_max_us=...; Imported trace metrics: ...
```

Для компактной таблицы по сохраненным логам:

```bash
scripts/summarize_ab_overhead.py /tmp/rt-supervised-ab-YYYYMMDD-HHMMSS
```

Интерпретация:

- сравнивайте `latency_min_avg_max_us` между `off`, `jsonl`, `prometheus`;
- `jsonl - off` показывает overhead записи trace summaries;
- `prometheus - jsonl` показывает overhead exporters/scrape/import;
- при больших выбросах повторите серию и смотрите не один `max`, а устойчивость `avg`.

## Ручной Просмотр Trace Summary

Smoke database обычно лежит здесь:

```text
/tmp/rt-tester-supervised-smoke.db
```

Для конкретной session:

```bash
cd /home/taranev/work_repos/rt/rt-tester/src/pc-receiver
python3 trace_summary.py /tmp/rt-tester-supervised-smoke.db --session-id SESSION_ID
```

`SESSION_ID` печатается каждым `run_supervised_smoke.sh`.

## Остановка Стенда

После тестов:

```bash
scripts/stop_supervised_stack.sh
scripts/stop_trace_prometheus_local.sh
```

`stop_supervised_stack.sh` останавливает только точные процессы supervised stack и
trace exporters, не используя `pkill -f`.

## Что Сохранять В Отчет

Для каждого измерения сохраняйте:

| Поле | Пример |
| --- | --- |
| branch/commit `beremiz-stand` | `feature/group-trace-prometheus`, commit hash |
| branch/commit `rt-supervisor` | commit hash на платах |
| branch/commit `rt-tester` | commit hash на ПК |
| board/kernel | VisionFive/RockPI, RT kernel |
| `SMOKE_GROUPS` или `AB_GROUPS` | `10` |
| `measurements-per-group` | `1500` |
| `TRACE_MODE` | `off`, `jsonl`, `prometheus` |
| `SESSION_ID` | напечатан smoke script |
| latency summary | `min / avg / max` |
| imported trace records | для trace Prometheus режима |
| trace stage summary | строки `trace=host/stage` или `trace_summary.py` |
