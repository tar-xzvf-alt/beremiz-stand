# Beremiz Project

В каталоге оставлен один проект:

```text
supervised-raw-plc/
```

Это PLC для текущего стенда с `rt-supervisor`:

- входные данные приходят из `/dev/shm/shmem_input`;
- выходной ответ пишется в `/dev/shm/shmem_output`;
- синхронизация с supervisor идет через futex;
- raw Ethernet, fragmentation, CRC и watchdog находятся вне Beremiz runtime.

Открыть в IDE:

```bash
beremiz beremiz-project/supervised-raw-plc
```

Runtime URI:

```text
ERPC://10.42.0.211:3000
```

Локальный `build/` не хранится в git. Для GUI-debug после remote-сборки выполните:

```bash
scripts/sync_supervised_debug_build_from_visionfive.sh
```
