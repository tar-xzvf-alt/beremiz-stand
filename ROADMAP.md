# RT Stand Packaging Roadmap

This document records the current execution plan for turning the RT stand
projects into reproducible ALT Linux packages and deployment flows.

## Step 0: Stand Network Baseline

Status: done and documented in [`NETWORK.md`](NETWORK.md).

Goal: before packaging work, the lab stand must be easy to access and both SBCs
must have internet access through the PC.

The current VisionFive 2 + RockPI 4 network setup is documented in
[`NETWORK.md`](NETWORK.md).

Required state:

- `ssh root@10.42.0.211` works from the PC.
- `ssh root@10.43.0.2` works from the PC.
- VisionFive 2 has internet access via the PC.
- RockPI 4 has internet access via VisionFive 2 and the PC.
- The network setup and recovery commands are documented.

## Step 1: Close Current Source Changes

Status: done. Runtime board selection and packaged runner work are present in
their respective repositories.

Completed scope:

- `rt-tester`: standalone GPIO flow uses packaged `rt-handler` by default.
- `rt-controller`: board selection is runtime-only via `controller-emu -b <board>`.

Verification used for `rt-controller`:

```bash
cmake -S . -B Build
cmake --build Build
ctest --test-dir Build --output-on-failure
Build/src/controller-emu --list-boards
```

Expected behavior:

- `controller-emu --list-boards` lists all board profiles.
- `controller-emu -i <iface>` without `-b` fails with a clear error.
- `controller-emu -i <iface> -b rockpi4` keeps the runtime board selection path.

## Step 2: Package `rt-controller`

Status: done for `rt-controller-0.1.1-alt1`; built for `riscv64` and
`aarch64`, installed on the stand.

The result is one generic RPM, not per-board builds.

Package contents:

- `/usr/bin/controller-emu`
- `/usr/share/rt-controller/scripts/*`
- `/usr/share/rt-controller/configs/*`
- docs through RPM `%doc`

Initial packaging choice:

- no systemd unit in the first package iteration;
- orchestration still provides interface, board, transport env and trace env.

## Step 3: Package `rt-supervisor`

Status: done for `rt-supervisor-0.1.2-alt1`; built for `riscv64` and
`aarch64`. The lifecycle regression is covered by package tests; repeating the
RockPI stand smoke was explicitly waived for this release.

The package supplies the supervised raw-Ethernet runtime side.

Package contents:

- `/usr/bin/alt-rt-supervisor`
- `/usr/bin/runtime` as the demo/runtime ABI example, unless split later;
- `/usr/share/rt-supervisor/scripts/*`
- `/usr/share/rt-supervisor/configs/*`
- docs through RPM `%doc`

Initial packaging choice:

- no systemd unit in the first package iteration;
- runtime path, interface and timeout remain orchestration/profile inputs.

## Step 4: Use Packaged Supervised Binaries

Status: done in `rt-tester` configs/runners for the RockPI supervised profile.
The packaged supervised smoke passed on 2026-07-16 with session `1784206831`.

`rt-tester-tools-0.1.1-alt1` packages the PC-side runners, receiver,
configuration examples and observability assets under `/usr/share/rt-tester-tools`.
Receiver logs and aggregate metrics are written to the user's XDG state
directory instead of the read-only package tree. Other stand state follows the
paths in the selected measurement config and defaults to `/tmp` in the examples.

The supervised stand configs and runners use packaged binaries:

- supervisor binary: `/usr/bin/alt-rt-supervisor`
- controller binary: `/usr/bin/controller-emu`
- scripts/configs from `/usr/share/rt-supervisor` and `/usr/share/rt-controller`

Keep source-tree deploy/build mode as an explicit development path.

Fresh-board package setup is documented in [`PACKAGED_SETUP.md`](PACKAGED_SETUP.md).

## Step 5: Decide `beremiz-stand` Package Scope

Status: done for `beremiz-stand-tools-0.1.2-alt1`. It installs
only PC-side scripts, profiles and docs under `/usr/share/beremiz-stand-tools`
with `/usr/bin/beremiz-stand` as a wrapper. The default universal configuration
is `/etc/beremiz-stand/stand.conf` and is preserved across RPM upgrades. PLC
project/runtime artifacts are not installed by the package.

The `doctor` command now treats missing Prometheus/Grafana binaries and stopped
optional endpoints consistently as `WARN` without affecting its exit status.
Required tools, paths, SSH checks and board names still fail the command.

PLC runtime pieces remain intentionally outside this package.

Implemented package shape:

- PC-side helper/tools package, for example `beremiz-stand-tools`;
- `scripts/stand.py`, profiles/templates and docs;
- no automatic deployment of PLC runtime as a system package yet.

## Step 6: End-to-End Validation

Status: package-only standalone GPIO and supervised raw-Ethernet flows are done.
The supervised packaged topology (RockPI supervisor, VisionFive 2 controller)
passed on 2026-07-16 with session `1784206831`. Source-flow comparison remains
available as a development path, not as a prerequisite for packaged smoke.

Validated modes:

- standalone GPIO on VisionFive 2 with installed `rt-handler` and no source deploy;
- supervised raw-Ethernet with installed `rt-controller` and `rt-supervisor`;
- previous source-tree flow remains documented separately for development.

## Step 7: Versioning, Tags, Pushes

Status: current release tags are `v0.1.6` for `rt-handler`, `v0.1.2` for
`rt-supervisor` and `beremiz-stand`, and `v0.1.1` for `rt-controller` and
`rt-tester`.

Rules:

- any tracked source or documentation change requires a `Version` bump;
- each new upstream version starts with `Release: alt1`;
- build RPMs for target architectures;
- install on boards;
- run smoke tests;
- tag and push only after validation.
