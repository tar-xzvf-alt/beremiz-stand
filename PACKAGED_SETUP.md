# Packaged RT Stand Setup

This is the minimal fresh-board checklist for the package-only stand flow. It
does not require a `beremiz-stand` or `rt-tester` Git checkout and assumes the
network from `NETWORK.md` is already restored.

The validated packaged topology is:

```text
PC -> VisionFive 2 (controller-emu, GPIO, network router) -> RockPI 4
   -> RockPI 4 (alt-rt-supervisor + /usr/bin/runtime)
```

This differs from the source profile `profiles/visionfive-rockpi.conf`, where
VisionFive is the supervisor and RockPI is the controller. Board role and
network-router role are independent; VisionFive remains the router in both.

## Packages

Current package set:

- `beremiz-stand-tools-0.1.2-alt1` for PC-side stand orchestration and docs.
- `rt-tester-tools-0.1.1-alt1` for PC-side measurements and observability data.
- `rt-handler-0.1.6-alt1` for standalone GPIO on VisionFive 2.
- `rt-controller-0.1.1-alt1` for the GPIO/raw-Ethernet controller role.
- `rt-supervisor-0.1.2-alt1` for the supervised runtime role.

Install the packages built by `gear-hsh` from the PC.

PC-side tools:

```bash
rpm -Uvh \
  /home/taranev/hasher/x86_64_chroot/repo/x86_64/RPMS.hasher/rt-tester-tools-0.1.1-alt1.noarch.rpm \
  /home/taranev/hasher/x86_64_chroot/repo/x86_64/RPMS.hasher/beremiz-stand-tools-0.1.2-alt1.noarch.rpm
rt-tester-run-stand --help
beremiz-stand --help
```

## `beremiz-stand` Package Contents

The RPM installs:

- `/usr/bin/beremiz-stand`;
- Python CLI modules, legacy shell helpers and supporting scripts under
  `/usr/share/beremiz-stand-tools/scripts/`;
- `/usr/share/beremiz-stand-tools/profiles/stand.conf.example`;
- `/etc/beremiz-stand/stand.conf` as `%config(noreplace)`;
- README, quickstart, guide, network, packaged setup, roadmap and test protocol
  as RPM documentation.

The RPM deliberately excludes `beremiz-project/`, PLC build/runtime artifacts,
`rt-supervisor` source/build trees, `.deps`, logs and measurement databases.
`rt-tester-tools`, `rt-controller` and `rt-supervisor` are separate packages.

Consequently, `sync-stand`, `build-plc`, `install-runtime-wrapper`,
`start-runtime`, `stop-runtime`, `deploy-plc`, `sync-plc-debug-build`,
`deploy-rt-supervisor`, `build-rt-supervisor` and `deploy-all` are source-only.
Do not use them as a package-only deployment procedure.

## Universal Stand Configuration

The profile selection precedence is:

1. explicit `--profile /path/to/stand.conf`;
2. `BEREMIZ_STAND_PROFILE`;
3. `/etc/beremiz-stand/stand.conf` through the packaged wrapper;
4. `profiles/visionfive-rockpi.conf` when running `scripts/stand.py` directly
   from a checkout with neither override.

Every profile must contain `[pc]`, `[supervisor]`, `[controller]` and
`[measurement]`. Commands validate required keys as they use them. Edit
`/etc/beremiz-stand/stand.conf` for the actual stand before using
`beremiz-stand`; RPM upgrades preserve it with `%config(noreplace)`. The clean
generic template remains in `/usr/share/beremiz-stand-tools/profiles/`.

VisionFive 2, controller side and standalone GPIO:

```bash
scp /home/taranev/hasher/riscv64_chroot/repo/riscv64/RPMS.hasher/rt-handler-0.1.6-alt1.riscv64.rpm \
    /home/taranev/hasher/riscv64_chroot/repo/riscv64/RPMS.hasher/rt-controller-0.1.1-alt1.riscv64.rpm \
    root@10.42.0.211:/tmp/
ssh root@10.42.0.211 'rpm -Uvh /tmp/rt-handler-0.1.6-alt1.riscv64.rpm /tmp/rt-controller-0.1.1-alt1.riscv64.rpm'
```

RockPI 4, supervised runtime side:

```bash
scp /home/taranev/hasher/aarch64_chroot/repo/aarch64/RPMS.hasher/rt-supervisor-0.1.2-alt1.aarch64.rpm \
    root@10.43.0.2:/tmp/
ssh root@10.43.0.2 'rpm -Uvh /tmp/rt-supervisor-0.1.2-alt1.aarch64.rpm'
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

Run the supervised smoke entirely from installed package content:

```bash
rt-tester-run-stand \
  --config /usr/share/rt-tester-tools/configs/stands/rockpi-plc-visionfive2-controller.conf \
  --groups 1 \
  --no-prometheus \
  --no-grafana \
  --skip-time-sync \
  --skip-pc-network-check
```

The packaged example currently has a lab-specific absolute PC network-check
path. `--skip-pc-network-check` is therefore required outside that checkout
until the example is generalized. It skips only that preflight; target startup,
measurement, logs and network counter checks still run.

After `beremiz-stand-tools` is installed, read-only packaged CLI checks are
available as:

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
ssh root@10.43.0.2 'pgrep -f "^/usr/bin/alt-rt-supervisor([[:space:]]|$)" || true; pgrep -x runtime || true'
```
