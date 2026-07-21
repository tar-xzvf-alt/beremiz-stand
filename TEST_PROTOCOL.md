# Протокол Измерений Supervised Raw Ethernet

Этот протокол проверяет supervised-схему Beremiz runtime + `rt-supervisor` +
Ethernet-контроллер и оценивает overhead trace-сбора.

## Что Измеряем

Основная метрика берется с Arduino через `rt-tester`: latency одного GPIO
цикла от импульса до ответа.

Trace-метрики собираются только на стороне supervisor'а (плата с Beremiz):

| Stage | Что измеряет |
| --- | --- |
| `ethernet_recv` | Приём запроса через raw socket |
| `shmem_input` | Запись в `/dev/shm/shmem_input` + futex wake |
| `runtime_wait` | Ожидание ответа от Beremiz runtime |
| `shmem_output` | Чтение ответа из `/dev/shm/shmem_output` |
| `ethernet_send` | Отправка ответа через raw socket |

Host в trace-данных теперь берётся через `gethostname()`, а не зашит
статически.

## Предусловия

На ПК:

```bash
cd /path/to/beremiz-stand
```

Проверить доступность плат:

```bash
ping -c 3 10.42.0.211
ssh root@10.42.0.211 true
ssh root@10.42.0.211 'ssh root@10.43.0.2 true'
```

На платах должны быть штатные binaries:

```text
RockPI:     /root/rt-supervisor/Build/src/alt-rt-supervisor
VisionFive: /root/rt-controller/Build/src/controller-emu
```

Arduino должен быть подключен к ПК как `/dev/ttyACM0`. Если порт другой:

```bash
ARDUINO_PORT=/dev/ttyACM1 scripts/run_supervised_smoke.sh
```

## Быстрая Sanity-Проверка

Запустить стенд без trace и сделать короткий smoke:

```bash
scripts/stand.py test-smoke --groups 2
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
scripts/stand.py test-trace --groups 2
```

Ожидаемые признаки успеха:

```text
trace_mode=prometheus
Imported trace metrics: 10
trace=ethernet_recv: groups=2 ...
trace=runtime_wait: groups=2 ...
```

Для 2 групп ожидается 10 imported trace records: 2 groups * 5 стадий.

Остановить локальный Prometheus и tunnels:

```bash
scripts/stand.py trace-stop
```

## Trace В Grafana

Для локального просмотра trace и Arduino latency через Grafana используйте
provisioned dashboard из `rt-tester/grafana`:

```bash
scripts/stand.py trace-start
scripts/stand.py grafana-start
```

Затем запустите trace smoke:

```bash
scripts/stand.py test-trace --groups 2
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

Выберите `session_id`, напечатанный smoke script. Для `SMOKE_GROUPS=2`
ожидается `Imported trace metrics: 10`.

Остановить Grafana:

```bash
scripts/stop_trace_grafana_local.sh
```

## A/B Overhead-Серия

Перед серией включите локальный trace Prometheus:

```bash
scripts/stand.py trace-start
```

Запустить короткую A/B серию:

```bash
scripts/stand.py test-ab --ab-groups 2 --ab-repeats 1
```

Для более устойчивой оценки используйте минимум 5 повторов:

```bash
scripts/stand.py test-ab --ab-groups 10 --ab-repeats 5
```

Результаты сохраняются в `/tmp/rt-supervised-ab-*`. В конце
печатается summary по каждому run.

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

```bash
scripts/stand.py trace-summary
scripts/stand.py trace-summary --session-id SESSION_ID
```

## Остановка Стенда

После тестов:

```bash
scripts/stand.py stop
scripts/stand.py trace-stop
```

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
