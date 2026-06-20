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
```

`doctor` проверяет локальные утилиты, SSH до VisionFive/RockPI, пути к
`rt-supervisor`, binaries, runtime wrapper, Arduino port и валидность board names.
Prometheus/Grafana в этом выводе считаются optional: они могут быть не запущены
до trace-теста.

Если после сброса Ethernet-настроек ПК/VisionFive не видно, сначала выполните:

```bash
scripts/stand.py network-restore
scripts/stand.py network-check
```

`network-restore` восстанавливает локальный Ethernet profile ПК и, если
VisionFive уже доступен по SSH, закрепляет адреса VisionFive/RockPI через
NetworkManager.

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

## 3. Запустить Обычный Smoke Без Trace

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

## 4. Запустить Trace Smoke

```bash
scripts/stand.py test-trace --groups 2
```

Эта команда сама стартует локальный trace Prometheus helper, затем запускает
smoke с `TRACE_MODE=prometheus` и импортирует trace metrics в SQLite.

Ожидаемый признак успеха для `--groups 2`:

```text
Imported trace metrics: 18
```

## 5. Открыть Grafana

```bash
scripts/stand.py grafana-start
```

Откройте:

```text
http://127.0.0.1:3001/d/rt-trace-stages
```

В dashboard выберите `session_id`, напечатанный `test-trace`.

## 6. Частые Команды

```bash
scripts/stand.py start
scripts/stand.py network-check
scripts/stand.py network-restore
scripts/stand.py deploy-rt-supervisor
scripts/stand.py build-rt-supervisor --clean-first
scripts/stand.py check
scripts/stand.py stop
scripts/stand.py trace-start
scripts/stand.py trace-stop
scripts/stand.py grafana-start
scripts/stand.py grafana-stop
```

## 7. Другой Profile

Скопируйте текущий profile и поменяйте IP/пути/board names:

```bash
cp profiles/visionfive-rockpi.conf profiles/my-stand.conf
scripts/stand.py --profile profiles/my-stand.conf doctor
```

## 8. Остановить Все После Тестов

```bash
scripts/stand.py stop
scripts/stand.py trace-stop
scripts/stand.py grafana-stop
```

## Что Пока Осталось В Shell Scripts

В этом milestone `stand.py` является удобным orchestration layer поверх старых
shell scripts. Это сделано намеренно: текущие проверенные команды остаются
рабочими, а пользователь получает одну точку входа. Следующий milestone будет
постепенно переносить логику из shell scripts внутрь Python orchestrator.
