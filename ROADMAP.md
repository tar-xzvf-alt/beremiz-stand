# RT Stand Packaging Roadmap

This document records the current execution plan for turning the RT stand
projects into reproducible ALT Linux packages and deployment flows.

## Step 0: Stand Network Baseline

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

Verify and commit the current source changes before new packaging work:

- `rt-tester`: standalone GPIO flow uses packaged `rt-handler` by default.
- `rt-controller`: board selection is runtime-only via `controller-emu -b <board>`.

Verify `rt-controller` in an environment with CMake:

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

Status: done for `rt-controller-0.1.0-alt2`; built for `riscv64` and
`aarch64`, installed on the stand. Version `0.1.0` is tagged as `v0.1.0`;
`alt2` is a packaging release bump.

Package one generic RPM, not per-board builds.

Expected package contents:

- `/usr/bin/controller-emu`
- `/usr/share/rt-controller/scripts/*`
- `/usr/share/rt-controller/configs/*`
- docs through RPM `%doc`

Initial packaging choice:

- no systemd unit in the first package iteration;
- orchestration still provides interface, board, transport env and trace env.

## Step 3: Package `rt-supervisor`

Status: done for `rt-supervisor-0.1.0-alt2`; built for `riscv64` and
`aarch64`, installed on the stand. Version `0.1.0` is tagged as `v0.1.0`;
`alt2` is a packaging release bump.

Package the supervised raw-Ethernet runtime side.

Expected package contents:

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
The packaged supervised smoke passed on 2026-07-14 with session `1784030431`.

After `rt-controller` and `rt-supervisor` packages exist, update supervised stand
configs and runners to prefer packaged binaries:

- supervisor binary: `/usr/bin/alt-rt-supervisor`
- controller binary: `/usr/bin/controller-emu`
- scripts/configs from `/usr/share/rt-supervisor` and `/usr/share/rt-controller`

Keep source-tree deploy/build mode as an explicit development path.

Fresh-board package setup is documented in [`PACKAGED_SETUP.md`](PACKAGED_SETUP.md).

## Step 5: Decide `beremiz-stand` Package Scope

Do not package PLC runtime pieces until the lower-level packages are stable.

Preferred first package shape:

- PC-side helper/tools package, for example `beremiz-stand-tools`;
- `scripts/stand.py`, profiles/templates and docs;
- no automatic deployment of PLC runtime as a system package yet.

## Step 6: End-to-End Validation

Run both modes on the real stand:

- standalone GPIO on VisionFive 2 with installed `rt-handler` and no source deploy;
- supervised raw-Ethernet with installed `rt-controller` and `rt-supervisor`;
- compare with the previous source-tree flow.

## Step 7: Versioning, Tags, Pushes

Rules:

- source/runtime behavior changes require `Version` bump;
- packaging-only changes can use `Release` bump;
- build RPMs for target architectures;
- install on boards;
- run smoke tests;
- tag and push only after validation.
