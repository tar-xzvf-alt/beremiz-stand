# Packaged RT Stand Setup

This is the minimal fresh-board checklist for the current packaged stand flow.
It assumes the network from `NETWORK.md` is already restored.

## Packages

Current validated package set:

- `beremiz-stand-tools-0.1.0-alt1` for PC-side stand orchestration.
- `rt-tester-tools-0.1.0-alt1` for PC-side measurements and observability data.
- `rt-handler-0.1.5-alt1` for standalone GPIO on VisionFive 2.
- `rt-controller-0.1.0-alt2` for the GPIO/raw-Ethernet controller role.
- `rt-supervisor-0.1.0-alt2` for the supervised runtime role.

Install the packages built by `gear-hsh` from the PC.

PC-side tools:

```bash
rpm -Uvh \
  /home/taranev/hasher/x86_64_chroot/repo/x86_64/RPMS.hasher/rt-tester-tools-0.1.0-alt1.noarch.rpm \
  /home/taranev/hasher/x86_64_chroot/repo/x86_64/RPMS.hasher/beremiz-stand-tools-0.1.0-alt1.noarch.rpm
rt-tester-run-stand --help
beremiz-stand --help
```

Edit `/etc/beremiz-stand/stand.conf` before commands that access the stand.
RPM upgrades preserve this file with `%config(noreplace)`. The original generic
template is available at
`/usr/share/beremiz-stand-tools/profiles/stand.conf.example`.

VisionFive 2, controller side and standalone GPIO:

```bash
scp /home/taranev/hasher/riscv64_chroot/repo/riscv64/RPMS.hasher/rt-handler-0.1.5-alt1.riscv64.rpm \
    /home/taranev/hasher/riscv64_chroot/repo/riscv64/RPMS.hasher/rt-controller-0.1.0-alt2.riscv64.rpm \
    root@10.42.0.211:/tmp/
ssh root@10.42.0.211 'rpm -Uvh --replacepkgs /tmp/rt-handler-0.1.5-alt1.riscv64.rpm /tmp/rt-controller-0.1.0-alt2.riscv64.rpm'
```

RockPI 4, supervised runtime side:

```bash
scp /home/taranev/hasher/aarch64_chroot/repo/aarch64/RPMS.hasher/rt-supervisor-0.1.0-alt2.aarch64.rpm \
    root@10.43.0.2:/tmp/
ssh root@10.43.0.2 'rpm -Uvh --replacepkgs /tmp/rt-supervisor-0.1.0-alt2.aarch64.rpm'
```

Install `rt-controller` on RockPI too only if RockPI is used as the controller
role in a swapped topology.

## Board Checks

VisionFive 2:

```bash
ssh root@10.42.0.211 'rpm -q rt-handler rt-controller; rt-handler -h >/dev/null; controller-emu --list-boards | grep -w visionfive2'
```

RockPI 4:

```bash
ssh root@10.43.0.2 'rpm -q rt-supervisor; alt-rt-supervisor -h >/dev/null; test -x /usr/bin/runtime'
```

## Packaged Smoke

Run the supervised smoke from `rt-tester` without source deploy/build:

```bash
cd /home/taranev/work_repos/rt/rt-tester
python3 scripts/run_stand_measurement.py \
  --config configs/stands/rockpi-plc-visionfive2-controller.conf \
  --groups 1 \
  --no-prometheus \
  --no-grafana \
  --skip-time-sync
```

After `beremiz-stand-tools` is installed, the packaged stand CLI is available as:

```bash
beremiz-stand status
beremiz-stand --profile /path/to/another-stand.conf status
```

Expected result:

- one group is stored in SQLite;
- target logs report zero anomaly matches;
- network error/drop counters do not grow;
- `Measurement completed successfully` is printed.

The complete PC and board packaged smoke was verified on 2026-07-16 with
session `1784206831` and 100 measurements in one group.

## Cleanup Check

After a smoke run, no target process should remain running:

```bash
ssh root@10.42.0.211 'pgrep -x controller-emu || true; pgrep -x runtime || true'
ssh root@10.43.0.2 'pgrep -f "^alt-rt-supervisor" || true; pgrep -x runtime || true'
```
