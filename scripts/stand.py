#!/usr/bin/env python3
import argparse
import configparser
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles" / "visionfive-rockpi.conf"
VALID_BOARDS = {
    "lichee",
    "radxa",
    "bcvm",
    "bvc",
    "bvc_arm",
    "starfive",
    "mangopi",
    "rockpi4",
    "repkapi4",
}
SSH_AUTO_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]


class StandError(Exception):
    pass


def load_profile(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not path.is_file():
        raise StandError(f"profile not found: {path}")
    cfg.read(path)
    for section in ("pc", "supervisor", "controller", "measurement"):
        if not cfg.has_section(section):
            raise StandError(f"profile is missing [{section}]")
    return cfg


def get(cfg: configparser.ConfigParser, section: str, key: str) -> str:
    value = cfg.get(section, key, fallback="").strip()
    if not value:
        raise StandError(f"profile value is missing: [{section}] {key}")
    return value


def opt(cfg: configparser.ConfigParser, section: str, key: str, default: str) -> str:
    return cfg.get(section, key, fallback=default).strip() or default


def run(cmd: list[str], env: dict[str, str] | None = None, check: bool = True) -> int:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    print("+ " + " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT, env=merged_env, check=False)
    if check and completed.returncode != 0:
        raise StandError(f"command failed with exit code {completed.returncode}")
    return completed.returncode


def run_or_dry(cmd: list[str], dry_run: bool) -> int:
    if dry_run:
        print("+ " + " ".join(cmd))
        return 0
    return run(cmd)


def capture(
    cmd: list[str],
    timeout: int = 10,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        completed = subprocess.run(
            cmd,
            cwd=ROOT,
            env=merged_env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "timeout"
    return completed.returncode, completed.stdout.strip()


def script(name: str) -> str:
    return str(ROOT / "scripts" / name)


def local_rt_supervisor(cfg: configparser.ConfigParser) -> Path:
    return Path(get(cfg, "pc", "rt_supervisor_dir"))


def supervisor(cfg: configparser.ConfigParser) -> str:
    return get(cfg, "supervisor", "ssh")


def controller(cfg: configparser.ConfigParser) -> str:
    return get(cfg, "controller", "ssh")


def beremiz_stand_dir(cfg: configparser.ConfigParser) -> str:
    return get(cfg, "supervisor", "beremiz_stand_dir")


def plc_project(cfg: configparser.ConfigParser) -> str:
    return get(cfg, "supervisor", "plc_project")


def runtime_dir(cfg: configparser.ConfigParser) -> str:
    return get(cfg, "supervisor", "runtime_dir")


def runtime_bind_ip(cfg: configparser.ConfigParser) -> str:
    return opt(
        cfg,
        "supervisor",
        "runtime_bind_ip",
        addr_host(get(cfg, "supervisor", "pc_addr")),
    )


def runtime_port(cfg: configparser.ConfigParser) -> str:
    return opt(cfg, "supervisor", "runtime_port", "3000")


def smoke_env(
    cfg: configparser.ConfigParser,
    args: argparse.Namespace,
    trace_mode: str,
    params_path: Path,
) -> dict[str, str]:
    env = {
        "RT_TESTER_DIR": get(cfg, "pc", "rt_tester_dir"),
        "ARDUINO_PORT": args.arduino_port or get(cfg, "pc", "arduino_port"),
        "SMOKE_GROUPS": str(args.groups or get(cfg, "measurement", "groups")),
        "SMOKE_PARAMS": str(params_path),
        "SUPERVISOR_BIN": get(cfg, "supervisor", "supervisor_bin"),
        "CONTROLLER_BIN": get(cfg, "controller", "controller_bin"),
        "RECEIVER_TIMEOUT_SEC": str(
            args.receiver_timeout_sec
            or opt(cfg, "measurement", "receiver_timeout_sec", "120")
        ),
        "TRACE_MODE": trace_mode,
    }
    if trace_mode == "prometheus":
        env["TRACE_PROMETHEUS_URL"] = get(cfg, "pc", "trace_prometheus_url")
    return env


def read_params(path: Path) -> list[str]:
    if not path.is_file():
        raise StandError(f"measurement params not found: {path}")
    return path.read_text(encoding="utf-8").splitlines()


def write_param(lines: list[str], key: str, value: str) -> list[str]:
    out: list[str] = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0].strip() == key:
            out.append(f"{key} = {value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key} = {value}")
    return out


def temp_params(cfg: configparser.ConfigParser, args: argparse.Namespace) -> object | None:
    src = Path(get(cfg, "measurement", "params"))
    interval_us = args.interval_us or opt(cfg, "measurement", "interval_us", "")
    measurements_per_group = args.measurements_per_group or opt(
        cfg, "measurement", "measurements_per_group", ""
    )
    overrides: list[tuple[str, str]] = []
    if interval_us:
        overrides.append(("measurement-interval-us", str(interval_us)))
    if measurements_per_group:
        overrides.append(("measurements-per-group", str(measurements_per_group)))
    if not overrides:
        return None

    lines = read_params(src)
    for key, value in overrides:
        lines = write_param(lines, key, value)

    tmp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="rt-stand-measurement-",
        suffix=".conf",
        delete=False,
    )
    tmp.write("\n".join(lines) + "\n")
    tmp.flush()
    tmp.close()
    return tmp


def params_for_run(cfg: configparser.ConfigParser, args: argparse.Namespace) -> tuple[Path, str | None]:
    tmp = temp_params(cfg, args)
    if tmp is None:
        return Path(get(cfg, "measurement", "params")), None
    return Path(tmp.name), tmp.name


def cleanup_temp(path: str | None) -> None:
    if path:
        try:
            Path(path).unlink()
        except FileNotFoundError:
            pass


def cmd_start(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    return run(
        [
            script("start_supervised_stack.sh"),
            supervisor(cfg),
            controller(cfg),
            get(cfg, "supervisor", "supervisor_bin"),
            get(cfg, "controller", "controller_bin"),
            get(cfg, "supervisor", "runtime_wrapper"),
            get(cfg, "supervisor", "iface"),
        ]
    )


def cmd_stop(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    return run([script("stop_supervised_stack.sh"), supervisor(cfg), controller(cfg)])


def cmd_check(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    env = {"ERPC_URL": get(cfg, "supervisor", "erpc_url")}
    return run([script("check_supervised_stack.sh"), supervisor(cfg), controller(cfg)], env=env)


def cmd_trace_start(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    env = {
        "VISIONFIVE": supervisor(cfg),
        "RT_TESTER_DIR": get(cfg, "pc", "rt_tester_dir"),
        "TRACE_PROMETHEUS_ADDR": get(cfg, "pc", "trace_prometheus_addr"),
    }
    return run([script("start_trace_prometheus_local.sh")], env=env)


def cmd_trace_stop(_cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    return run([script("stop_trace_prometheus_local.sh")])


def cmd_grafana_start(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    host, port = get(cfg, "pc", "trace_grafana_addr").rsplit(":", 1)
    env = {
        "RT_TESTER_DIR": get(cfg, "pc", "rt_tester_dir"),
        "TRACE_GRAFANA_ADDR": host,
        "TRACE_GRAFANA_PORT": port,
    }
    return run([script("start_trace_grafana_local.sh")], env=env)


def cmd_grafana_stop(_cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    return run([script("stop_trace_grafana_local.sh")])


def cmd_test_smoke(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    params, tmp_path = params_for_run(cfg, args)
    try:
        env = smoke_env(cfg, args, "off", params)
        return run([script("run_supervised_smoke.sh"), supervisor(cfg), controller(cfg)], env=env)
    finally:
        cleanup_temp(tmp_path)


def cmd_test_trace(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    params, tmp_path = params_for_run(cfg, args)
    try:
        if not args.no_trace_start:
            cmd_trace_start(cfg, args)
        env = smoke_env(cfg, args, "prometheus", params)
        return run([script("run_supervised_smoke.sh"), supervisor(cfg), controller(cfg)], env=env)
    finally:
        cleanup_temp(tmp_path)


def cmd_sync_stand(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [script("sync_to_visionfive.sh"), supervisor(cfg), beremiz_stand_dir(cfg)],
        args.dry_run,
    )


def cmd_build_plc(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("build_supervised_raw_on_visionfive.sh"),
            supervisor(cfg),
            beremiz_stand_dir(cfg),
            plc_project(cfg),
        ],
        args.dry_run,
    )


def cmd_install_runtime_wrapper(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("install_supervised_runtime_wrapper_on_visionfive.sh"),
            supervisor(cfg),
            runtime_dir(cfg),
            runtime_bind_ip(cfg),
            runtime_port(cfg),
            beremiz_stand_dir(cfg),
        ],
        args.dry_run,
    )


def cmd_start_runtime(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("start_runtime_on_visionfive.sh"),
            supervisor(cfg),
            runtime_dir(cfg),
            runtime_bind_ip(cfg),
            runtime_port(cfg),
            beremiz_stand_dir(cfg),
        ],
        args.dry_run,
    )


def cmd_stop_runtime(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("stop_runtime_on_visionfive.sh"),
            supervisor(cfg),
            runtime_dir(cfg),
        ],
        args.dry_run,
    )


def cmd_deploy_plc(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("deploy_run_supervised_raw_on_visionfive_runtime.sh"),
            supervisor(cfg),
            beremiz_stand_dir(cfg),
            get(cfg, "supervisor", "erpc_url"),
            plc_project(cfg),
        ],
        args.dry_run,
    )


def cmd_sync_plc_debug_build(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    return run_or_dry(
        [
            script("sync_supervised_debug_build_from_visionfive.sh"),
            supervisor(cfg),
            beremiz_stand_dir(cfg),
        ],
        args.dry_run,
    )


def deploy_all_dry_run(args: argparse.Namespace) -> int:
    print("+ scripts/stand.py stop")
    print("+ scripts/stand.py network-check")
    if not args.skip_rt_supervisor:
        print("+ scripts/stand.py deploy-rt-supervisor")
        build_cmd = "scripts/stand.py build-rt-supervisor"
        if args.clean_first:
            build_cmd += " --clean-first"
        print("+ " + build_cmd)
    if not args.skip_plc:
        print("+ scripts/stand.py sync-stand")
        print("+ scripts/stand.py build-plc")
        print("+ scripts/stand.py install-runtime-wrapper")
        print("+ scripts/stand.py start-runtime")
        print("+ scripts/stand.py deploy-plc")
    if not args.skip_smoke:
        smoke = "test-trace" if args.trace_smoke else "test-smoke"
        print(f"+ scripts/stand.py {smoke} --groups {args.groups}")
    return 0


def cmd_deploy_all(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    if args.dry_run:
        return deploy_all_dry_run(args)

    cmd_stop(cfg, args)
    if cmd_network_check(cfg, args) != 0:
        return 1

    if not args.skip_rt_supervisor:
        cmd_deploy_rt_supervisor(
            cfg,
            argparse.Namespace(
                supervisor_only=False,
                controller_only=False,
                dry_run=False,
            ),
        )
        cmd_build_rt_supervisor(
            cfg,
            argparse.Namespace(
                supervisor_only=False,
                controller_only=False,
                clean_first=args.clean_first,
                dry_run=False,
            ),
        )

    if not args.skip_plc:
        plc_args = argparse.Namespace(dry_run=False)
        cmd_sync_stand(cfg, plc_args)
        cmd_build_plc(cfg, plc_args)
        cmd_install_runtime_wrapper(cfg, plc_args)
        cmd_start_runtime(cfg, plc_args)
        cmd_deploy_plc(cfg, plc_args)

    if args.skip_smoke:
        return 0

    smoke_args = argparse.Namespace(
        groups=args.groups,
        interval_us=None,
        measurements_per_group=None,
        arduino_port=None,
        receiver_timeout_sec=None,
        no_trace_start=False,
    )
    if args.trace_smoke:
        return cmd_test_trace(cfg, smoke_args)
    return cmd_test_smoke(cfg, smoke_args)


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def write_command_output(path: Path, cmd: list[str], code: int, output: str) -> None:
    path.write_text(
        "+ " + " ".join(cmd) + "\n"
        f"exit_code={code}\n\n"
        + output
        + "\n",
        encoding="utf-8",
    )


def remote_log_command(paths: list[str], lines: int) -> str:
    quoted_paths = " ".join(shlex.quote(path) for path in paths)
    return (
        "set +e; "
        "echo '== host =='; hostname; "
        "echo '== date =='; date; "
        "echo '== uname =='; uname -a; "
        "echo '== addresses =='; ip -br addr; "
        "echo '== processes =='; ps -eo pid,tid,cls,rtprio,pri,psr,comm,args; "
        f"for f in {quoted_paths}; do "
        "echo; echo \"== $f ==\"; "
        "if [ -e \"$f\" ]; then "
        f"tail -n {lines} \"$f\"; "
        "else echo 'missing'; fi; "
        "done"
    )


def cmd_collect_logs(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    outdir = Path(args.output or f"/tmp/rt-stand-logs-{timestamp()}")
    outdir.mkdir(parents=True, exist_ok=True)

    check_cmd = [script("check_supervised_stack.sh"), supervisor(cfg), controller(cfg)]
    code, out = capture(
        check_cmd,
        timeout=60,
        env={"ERPC_URL": get(cfg, "supervisor", "erpc_url")},
    )
    write_command_output(outdir / "check_supervised_stack.txt", check_cmd, code, out)

    network_cmd = [
        str(Path(__file__).resolve()),
        "--profile",
        args.profile,
        "network-check",
    ]
    code, out = capture(network_cmd, timeout=60)
    write_command_output(outdir / "network_check.txt", network_cmd, code, out)

    time_cmd = [
        str(Path(__file__).resolve()),
        "--profile",
        args.profile,
        "time-check",
    ]
    code, out = capture(time_cmd, timeout=60)
    write_command_output(outdir / "time_check.txt", time_cmd, code, out)

    visionfive_logs = [
        "/root/alt-rt-supervisor.log",
        f"{runtime_dir(cfg)}/beremiz_service.log",
        "/root/rt-trace-exporter.log",
        "/tmp/rt-supervisor-trace.jsonl",
    ]
    code, out = capture(
        [
            "ssh",
            *SSH_AUTO_OPTS,
            supervisor(cfg),
            remote_log_command(visionfive_logs, args.lines),
        ],
        timeout=60,
    )
    write_command_output(
        outdir / "visionfive.txt",
        ["ssh", supervisor(cfg), "<snapshot>"],
        code,
        out,
    )

    rockpi_logs = [
        "/root/controller-emu.log",
        "/root/rt-trace-exporter.log",
        "/tmp/controller-emu-trace.jsonl",
    ]
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    rockpi_command = remote_log_command(rockpi_logs, args.lines)
    remote_cmd = (
        f"ssh {inner_opts} {shlex.quote(controller(cfg))} "
        f"{shlex.quote(rockpi_command)}"
    )
    code, out = capture(
        ["ssh", *SSH_AUTO_OPTS, get(cfg, "controller", "ssh_jump"), remote_cmd],
        timeout=60,
    )
    write_command_output(
        outdir / "rockpi.txt",
        ["ssh", get(cfg, "controller", "ssh_jump"), "ssh", controller(cfg), "<snapshot>"],
        code,
        out,
    )

    print(f"Collected logs in {outdir}")
    return 0


def selected_boards(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.supervisor_only and args.controller_only:
        raise StandError("choose only one of --supervisor-only or --controller-only")
    return not args.controller_only, not args.supervisor_only


def create_rt_supervisor_archive(source: Path) -> Path:
    if not source.is_dir():
        raise StandError(f"local rt-supervisor dir not found: {source}")

    archive = tempfile.NamedTemporaryFile(
        prefix="rt-supervisor-transfer-",
        suffix=".tgz",
        delete=False,
    )
    archive.close()
    run(
        [
            "tar",
            "--exclude=./.git",
            "--exclude=./Build",
            "--exclude=__pycache__",
            "-czf",
            archive.name,
            "-C",
            str(source),
            ".",
        ]
    )
    return Path(archive.name)


def assert_safe_remote_dir(path: str) -> None:
    unsafe = {"", "/", "/root", "/home", "/tmp"}
    if path in unsafe or not path.startswith("/"):
        raise StandError(f"refusing unsafe remote directory: {path}")


def scp_to(host: str, local: Path, remote: str) -> int:
    cmd = ["scp", *SSH_AUTO_OPTS]
    cmd.extend([str(local), f"{host}:{remote}"])
    return run(cmd)


def scp_to_via_jump(jump: str, host: str, local: Path, remote: str) -> int:
    jump_archive = f"/tmp/{Path(remote).name}"
    scp_to(jump, local, jump_archive)
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    remote_target = shlex.quote(f"{host}:{remote}")
    return ssh_run(
        jump,
        "set -eu; "
        f"scp {inner_opts} {shlex.quote(jump_archive)} {remote_target}; "
        f"rm -f {shlex.quote(jump_archive)}",
    )


def ssh_run(host: str, command: str) -> int:
    return run(["ssh", *SSH_AUTO_OPTS, host, command])


def ssh_jump_run(jump: str, host: str, command: str) -> int:
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    remote_cmd = f"ssh {inner_opts} {shlex.quote(host)} {shlex.quote(command)}"
    return run(["ssh", *SSH_AUTO_OPTS, jump, remote_cmd])


def deploy_archive(host: str, remote_dir: str, archive: Path, jump: str | None = None) -> None:
    assert_safe_remote_dir(remote_dir)
    remote_archive = "/tmp/rt-supervisor-transfer.tgz"
    if jump:
        scp_to_via_jump(jump, host, archive, remote_archive)
    else:
        scp_to(host, archive, remote_archive)
    remote_command = (
        "set -eu; "
        f"rm -rf {shlex.quote(remote_dir)}; "
        f"mkdir -p {shlex.quote(remote_dir)}; "
        f"tar -xzf {remote_archive} -C {shlex.quote(remote_dir)}; "
        f"rm -f {remote_archive}"
    )
    if jump:
        ssh_jump_run(jump, host, remote_command)
    else:
        ssh_run(host, remote_command)


def cmake_build_command(remote_dir: str, board: str, target: str, clean: bool) -> str:
    assert_safe_remote_dir(remote_dir)
    build = f"cmake --build Build --target {shlex.quote(target)}"
    if clean:
        build += " --clean-first"
    return (
        "set -eu; "
        f"cd {shlex.quote(remote_dir)}; "
        f"cmake -S . -B Build -DBOARD={shlex.quote(board)}; "
        f"{build}"
    )


def cmd_deploy_rt_supervisor(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    deploy_supervisor, deploy_controller = selected_boards(args)
    archive = create_rt_supervisor_archive(local_rt_supervisor(cfg))
    try:
        if args.dry_run:
            print(f"Created archive: {archive}")
            if deploy_supervisor:
                print(
                    "Would deploy to VisionFive: "
                    f"{supervisor(cfg)}:{get(cfg, 'supervisor', 'rt_supervisor_dir')}"
                )
            if deploy_controller:
                print(
                    "Would deploy to RockPI via VisionFive: "
                    f"{controller(cfg)}:{get(cfg, 'controller', 'rt_supervisor_dir')}"
                )
            return 0
        if deploy_supervisor:
            print("== Deploy rt-supervisor to VisionFive ==")
            deploy_archive(
                supervisor(cfg),
                get(cfg, "supervisor", "rt_supervisor_dir"),
                archive,
            )
        if deploy_controller:
            print("== Deploy rt-supervisor to RockPI ==")
            deploy_archive(
                controller(cfg),
                get(cfg, "controller", "rt_supervisor_dir"),
                archive,
                jump=get(cfg, "controller", "ssh_jump"),
            )
    finally:
        archive.unlink(missing_ok=True)
    return 0


def cmd_build_rt_supervisor(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    build_supervisor, build_controller = selected_boards(args)
    supervisor_command = cmake_build_command(
        get(cfg, "supervisor", "rt_supervisor_dir"),
        get(cfg, "supervisor", "board"),
        "alt-rt-supervisor",
        args.clean_first,
    )
    controller_command = cmake_build_command(
        get(cfg, "controller", "rt_supervisor_dir"),
        get(cfg, "controller", "board"),
        "controller-emu",
        args.clean_first,
    )
    if args.dry_run:
        if build_supervisor:
            print(f"Would run on VisionFive {supervisor(cfg)}: {supervisor_command}")
        if build_controller:
            print(
                "Would run on RockPI "
                f"{controller(cfg)} via {get(cfg, 'controller', 'ssh_jump')}: "
                f"{controller_command}"
            )
        return 0
    if build_supervisor:
        print("== Build alt-rt-supervisor on VisionFive ==")
        ssh_run(supervisor(cfg), supervisor_command)
    if build_controller:
        print("== Build controller-emu on RockPI ==")
        ssh_jump_run(
            get(cfg, "controller", "ssh_jump"),
            controller(cfg),
            controller_command,
        )
    return 0


def check_local_tool(name: str) -> bool:
    return shutil.which(name) is not None


def check_path(path: Path) -> bool:
    return path.exists()


def print_check(ok: bool, label: str, detail: str = "") -> bool:
    status = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    return ok


def print_status(ok: bool, label: str, detail: str = "", optional: bool = False) -> bool:
    status = "OK" if ok else ("WARN" if optional else "FAIL")
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    return ok or optional


def first_line(output: str) -> str:
    for line in output.splitlines():
        if line.strip():
            return line.strip()
    return ""


def last_line(output: str) -> str:
    for line in reversed(output.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def pgrep_executable_pattern(path: str) -> str:
    name = Path(path).name
    if not name:
        return path
    return f"/{re.escape(name)}([[:space:]]|$)"


def ssh_check(host: str, command: str, timeout: int = 10) -> tuple[bool, str]:
    code, out = capture(["ssh", *SSH_AUTO_OPTS, host, command], timeout=timeout)
    return code == 0, out


def ssh_jump_check(jump: str, host: str, command: str, timeout: int = 10) -> tuple[bool, str]:
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    remote_cmd = f"ssh {inner_opts} {shlex.quote(host)} {shlex.quote(command)}"
    code, out = capture(["ssh", *SSH_AUTO_OPTS, jump, remote_cmd], timeout=timeout)
    return code == 0, out


def http_check(url: str, timeout: int = 3) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout).read(1)
    except Exception:
        return False
    return True


def addr_host(addr: str) -> str:
    return addr.split("/", 1)[0]


def contains_addr(output: str, addr: str) -> bool:
    return addr in output or addr_host(addr) in output


def parse_epoch(output: str) -> int:
    for line in output.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    raise StandError(f"could not parse epoch from output: {output}")


def remote_time_skew(host: str) -> tuple[bool, int | None, str]:
    start = time.time()
    ok, out = ssh_check(host, "date -u +%s", timeout=10)
    end = time.time()
    if not ok:
        return False, None, out
    local_epoch = round((start + end) / 2)
    return True, parse_epoch(out) - local_epoch, out


def remote_time_skew_via_jump(jump: str, host: str) -> tuple[bool, int | None, str]:
    start = time.time()
    ok, out = ssh_jump_check(jump, host, "date -u +%s", timeout=10)
    end = time.time()
    if not ok:
        return False, None, out
    local_epoch = round((start + end) / 2)
    return True, parse_epoch(out) - local_epoch, out


def set_remote_time(host: str, epoch: int, timeout: int = 20) -> tuple[bool, str]:
    command = f"date -u -s @{epoch}; date -u +%s"
    return ssh_check(host, command, timeout=timeout)


def set_remote_time_via_jump(
    jump: str,
    host: str,
    epoch: int,
    timeout: int = 20,
) -> tuple[bool, str]:
    command = f"date -u -s @{epoch}; date -u +%s"
    return ssh_jump_check(jump, host, command, timeout=timeout)


def cmd_time_check(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    max_skew = args.max_skew_sec
    checks: list[bool] = []

    print("== Local ==")
    print(datetime.now().astimezone().isoformat())

    print("\n== VisionFive ==")
    ok, skew, out = remote_time_skew(supervisor(cfg))
    if ok and skew is not None:
        checks.append(
            print_check(abs(skew) <= max_skew, f"skew <= {max_skew}s", f"{skew:+d}s")
        )
    else:
        print(out)
        checks.append(print_check(False, "read VisionFive time"))

    print("\n== RockPI ==")
    ok, skew, out = remote_time_skew_via_jump(get(cfg, "controller", "ssh_jump"), controller(cfg))
    if ok and skew is not None:
        checks.append(
            print_check(abs(skew) <= max_skew, f"skew <= {max_skew}s", f"{skew:+d}s")
        )
    else:
        print(out)
        checks.append(print_check(False, "read RockPI time"))

    failures = sum(1 for ok in checks if not ok)
    if failures:
        print(f"\nTime check found {failures} problem(s)")
        return 1
    print("\nTime check passed")
    return 0


def cmd_time_restore(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    epoch = int(time.time())
    checks: list[bool] = []

    print(f"== Set board clocks to PC epoch {epoch} ==")

    print("\n== VisionFive ==")
    ok, out = set_remote_time(supervisor(cfg), epoch)
    print(out)
    checks.append(print_check(ok, "set VisionFive time"))

    print("\n== RockPI ==")
    ok, out = set_remote_time_via_jump(get(cfg, "controller", "ssh_jump"), controller(cfg), epoch)
    print(out)
    checks.append(print_check(ok, "set RockPI time"))

    if not all(checks):
        print("\nTime restore failed")
        return 1

    return cmd_time_check(cfg, argparse.Namespace(max_skew_sec=args.max_skew_sec))


def nmcli_restore_connection(connection: str, iface: str, addr: str) -> int:
    run(
        [
            "nmcli",
            "connection",
            "modify",
            connection,
            "connection.interface-name",
            iface,
            "connection.autoconnect",
            "yes",
            "ipv4.method",
            "manual",
            "ipv4.addresses",
            addr,
            "ipv4.never-default",
            "yes",
            "ipv6.method",
            "link-local",
        ]
    )
    return run(["nmcli", "connection", "up", connection, "ifname", iface])


def nmcli_restore_route(connection: str, route: str, gateway: str) -> int:
    route_value = f"{route} {gateway}"
    run(["nmcli", "connection", "modify", connection, "ipv4.routes", route_value])
    return run(["nmcli", "connection", "up", connection])


def remote_restore_network(
    host: str,
    connection: str,
    iface: str,
    addr: str,
    timeout: int = 20,
) -> tuple[bool, str]:
    command = (
        "set -eu; "
        "if command -v nmcli >/dev/null 2>&1; then "
        f"if ! nmcli -t -f NAME connection show | grep -Fx -- '{connection}' >/dev/null; then "
        f"nmcli connection add type ethernet ifname '{iface}' con-name '{connection}'; "
        "fi; "
        f"nmcli connection modify '{connection}' "
        f"connection.interface-name '{iface}' "
        "connection.autoconnect yes "
        "ipv4.method manual "
        f"ipv4.addresses '{addr}' "
        "ipv4.never-default yes "
        "ipv6.method disabled; "
        f"nmcli connection up '{connection}' ifname '{iface}' || "
        f"{{ ip addr replace '{addr}' dev '{iface}'; ip link set '{iface}' up; }}; "
        "else "
        f"ip addr replace '{addr}' dev '{iface}'; ip link set '{iface}' up; "
        "fi; "
        f"ip -br addr show '{iface}'"
    )
    return ssh_check(host, command, timeout=timeout)


def remote_restore_network_via_jump(
    jump: str,
    host: str,
    connection: str,
    iface: str,
    addr: str,
    timeout: int = 20,
) -> tuple[bool, str]:
    command = (
        "set -eu; "
        "if command -v nmcli >/dev/null 2>&1; then "
        f"if ! nmcli -t -f NAME connection show | grep -Fx -- '{connection}' >/dev/null; then "
        f"nmcli connection add type ethernet ifname '{iface}' con-name '{connection}'; "
        "fi; "
        f"nmcli connection modify '{connection}' "
        f"connection.interface-name '{iface}' "
        "connection.autoconnect yes "
        "ipv4.method manual "
        f"ipv4.addresses '{addr}' "
        "ipv4.never-default yes "
        "ipv6.method disabled; "
        f"nmcli connection up '{connection}' ifname '{iface}' || "
        f"{{ ip addr replace '{addr}' dev '{iface}'; ip link set '{iface}' up; }}; "
        "else "
        f"ip addr replace '{addr}' dev '{iface}'; ip link set '{iface}' up; "
        "fi; "
        f"ip -br addr show '{iface}'"
    )
    return ssh_jump_check(jump, host, command, timeout=timeout)


def remote_enable_ip_forward(host: str, persist: bool, timeout: int = 10) -> tuple[bool, str]:
    command = "set -eu; sysctl -w net.ipv4.ip_forward=1; "
    if persist:
        command += (
            "printf '%s\\n' 'net.ipv4.ip_forward = 1' "
            "> /etc/sysctl.d/99-rt-stand-forward.conf; "
        )
    command += "sysctl net.ipv4.ip_forward"
    return ssh_check(host, command, timeout=timeout)


def remote_restore_route_via_jump(
    jump: str,
    host: str,
    connection: str,
    route: str,
    gateway: str,
    timeout: int = 20,
) -> tuple[bool, str]:
    route_value = f"{route} {gateway}"
    command = (
        "set -eu; "
        "if command -v nmcli >/dev/null 2>&1; then "
        f"nmcli connection modify {shlex.quote(connection)} "
        f"ipv4.routes {shlex.quote(route_value)}; "
        "fi; "
        f"ip route replace {shlex.quote(route)} via {shlex.quote(gateway)}; "
        "ip route"
    )
    return ssh_jump_check(jump, host, command, timeout=timeout)


def install_controller_ssh_key(cfg: configparser.ConfigParser) -> tuple[bool, str]:
    key_path = Path(get(cfg, "pc", "ssh_public_key"))
    if not key_path.is_file():
        return False, f"SSH public key not found: {key_path}"
    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        return False, f"SSH public key is empty: {key_path}"
    command = (
        "set -eu; "
        "mkdir -p /root/.ssh; chmod 700 /root/.ssh; "
        "touch /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys; "
        f"grep -qxF {shlex.quote(key)} /root/.ssh/authorized_keys || "
        f"printf '%s\\n' {shlex.quote(key)} >> /root/.ssh/authorized_keys"
    )
    return ssh_jump_check(
        get(cfg, "controller", "ssh_jump"),
        controller(cfg),
        command,
        timeout=20,
    )


def cmd_network_check(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    checks: list[bool] = []

    pc_iface = get(cfg, "pc", "ethernet_iface")
    pc_addr = get(cfg, "pc", "ethernet_addr")
    pc_controller_route = get(cfg, "pc", "controller_route")
    pc_controller_gateway = get(cfg, "pc", "controller_gateway")
    sup = supervisor(cfg)
    sup_pc_iface = get(cfg, "supervisor", "pc_iface")
    sup_pc_addr = get(cfg, "supervisor", "pc_addr")
    sup_ctrl_iface = get(cfg, "supervisor", "controller_iface")
    sup_ctrl_addr = get(cfg, "supervisor", "controller_addr")
    ctrl = controller(cfg)
    ctrl_iface = get(cfg, "controller", "iface")
    ctrl_addr = get(cfg, "controller", "addr")
    ctrl_pc_route = get(cfg, "controller", "pc_route")
    ctrl_pc_gateway = get(cfg, "controller", "pc_gateway")
    jump = get(cfg, "controller", "ssh_jump")

    print("== PC Ethernet ==")
    code, out = capture(["ip", "-br", "addr", "show", pc_iface])
    print(out)
    checks.append(print_check(code == 0 and contains_addr(out, pc_addr), f"{pc_iface} has {pc_addr}"))
    code, out = capture(["ip", "route", "get", addr_host(ctrl_addr)])
    print(out)
    checks.append(
        print_check(
            code == 0 and pc_controller_gateway in out and pc_iface in out,
            f"PC route {pc_controller_route} via {pc_controller_gateway}",
        )
    )

    print("\n== PC -> VisionFive ==")
    code, out = capture(["ping", "-c", "3", "-W", "2", addr_host(sup_pc_addr)], timeout=10)
    checks.append(print_check(code == 0, f"ping {addr_host(sup_pc_addr)}", out.splitlines()[-1] if out else ""))
    ok, out = ssh_check(sup, f"ip -br addr show {sup_pc_iface}; ip -br addr show {sup_ctrl_iface}")
    print(out)
    checks.append(print_check(ok and contains_addr(out, sup_pc_addr), f"VisionFive {sup_pc_iface} has {sup_pc_addr}"))
    checks.append(print_check(ok and contains_addr(out, sup_ctrl_addr), f"VisionFive {sup_ctrl_iface} has {sup_ctrl_addr}"))
    ok, out = ssh_check(sup, "sysctl -n net.ipv4.ip_forward")
    checks.append(print_check(ok and out.strip() == "1", "VisionFive IPv4 forwarding enabled", out))

    print("\n== VisionFive -> RockPI ==")
    ok, out = ssh_jump_check(jump, ctrl, f"ip -br addr show {ctrl_iface}")
    print(out)
    checks.append(print_check(ok and contains_addr(out, ctrl_addr), f"RockPI {ctrl_iface} has {ctrl_addr}"))
    ok_route, route_out = ssh_jump_check(jump, ctrl, f"ip route get {addr_host(pc_addr)}")
    print(route_out)
    checks.append(
        print_check(
            ok_route and ctrl_pc_gateway in route_out,
            f"RockPI route {ctrl_pc_route} via {ctrl_pc_gateway}",
        )
    )
    ok, out = ssh_check(sup, f"ping -c 3 -W 2 {addr_host(ctrl_addr)}")
    checks.append(print_check(ok, f"VisionFive ping RockPI {addr_host(ctrl_addr)}", out.splitlines()[-1] if out else ""))

    print("\n== PC -> RockPI Direct ==")
    code, out = capture(["ping", "-c", "3", "-W", "2", addr_host(ctrl_addr)], timeout=10)
    checks.append(print_check(code == 0, f"PC ping RockPI {addr_host(ctrl_addr)}", out.splitlines()[-1] if out else ""))
    code, out = capture(["ssh", *SSH_AUTO_OPTS, controller(cfg), "true"], timeout=10)
    checks.append(print_check(code == 0, f"PC ssh {controller(cfg)}", out))

    failures = sum(1 for ok in checks if not ok)
    if failures:
        print(f"\nNetwork check found {failures} problem(s)")
        return 1
    print("\nNetwork check passed")
    return 0


def cmd_network_restore(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    print("== Restore PC Ethernet ==")
    nmcli_restore_connection(
        get(cfg, "pc", "ethernet_connection"),
        get(cfg, "pc", "ethernet_iface"),
        get(cfg, "pc", "ethernet_addr"),
    )
    nmcli_restore_route(
        get(cfg, "pc", "ethernet_connection"),
        get(cfg, "pc", "controller_route"),
        get(cfg, "pc", "controller_gateway"),
    )

    sup = supervisor(cfg)
    ok, out = ssh_check(sup, "true", timeout=5)
    if not ok:
        print("\nVisionFive is still unreachable over SSH after PC Ethernet restore.")
        print("Use serial/UART or board console to restore its PC-facing address:")
        print(
            "  "
            f"nmcli connection modify {get(cfg, 'supervisor', 'pc_connection')} "
            f"ipv4.method manual ipv4.addresses {get(cfg, 'supervisor', 'pc_addr')} "
            "ipv4.never-default yes ipv6.method disabled"
        )
        print(
            "  "
            f"nmcli connection up {get(cfg, 'supervisor', 'pc_connection')} "
            f"ifname {get(cfg, 'supervisor', 'pc_iface')}"
        )
        return 1

    print("\n== Restore VisionFive Interfaces ==")
    for connection, iface, addr in (
        (
            get(cfg, "supervisor", "pc_connection"),
            get(cfg, "supervisor", "pc_iface"),
            get(cfg, "supervisor", "pc_addr"),
        ),
        (
            get(cfg, "supervisor", "controller_connection"),
            get(cfg, "supervisor", "controller_iface"),
            get(cfg, "supervisor", "controller_addr"),
        ),
    ):
        ok, out = remote_restore_network(sup, connection, iface, addr)
        print(out)
        if not ok:
            raise StandError(f"failed to restore VisionFive {iface}")

    ok, out = remote_enable_ip_forward(
        sup,
        opt(cfg, "supervisor", "enable_ip_forward", "yes").lower() in {"1", "yes", "true", "on"},
    )
    print(out)
    if not ok:
        raise StandError("failed to enable VisionFive IPv4 forwarding")

    print("\n== Restore RockPI Interface If Reachable ==")
    ok, out = ssh_jump_check(get(cfg, "controller", "ssh_jump"), controller(cfg), "true", timeout=5)
    if not ok:
        print("RockPI is not reachable via VisionFive; skipping RockPI restore")
        return cmd_network_check(cfg, _args)

    ok, out = remote_restore_network_via_jump(
        get(cfg, "controller", "ssh_jump"),
        controller(cfg),
        get(cfg, "controller", "connection"),
        get(cfg, "controller", "iface"),
        get(cfg, "controller", "addr"),
    )
    print(out)
    if not ok:
        raise StandError("failed to restore RockPI interface")

    ok, out = remote_restore_route_via_jump(
        get(cfg, "controller", "ssh_jump"),
        controller(cfg),
        get(cfg, "controller", "connection"),
        get(cfg, "controller", "pc_route"),
        get(cfg, "controller", "pc_gateway"),
    )
    print(out)
    if not ok:
        raise StandError("failed to restore RockPI reverse route")

    ok, out = install_controller_ssh_key(cfg)
    if ok:
        print("Installed PC SSH public key on RockPI")
    else:
        print(f"RockPI SSH key install skipped/failed: {out}")

    return cmd_network_check(cfg, _args)


def cmd_status(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    checks: list[bool] = []
    sup = supervisor(cfg)
    ctrl = controller(cfg)
    ctrl_addr = get(cfg, "controller", "addr")
    pc_controller_gateway = get(cfg, "pc", "controller_gateway")
    pc_iface = get(cfg, "pc", "ethernet_iface")

    print("== Network ==")
    code, out = capture(["ip", "route", "get", addr_host(ctrl_addr)], timeout=5)
    checks.append(
        print_status(
            code == 0 and pc_controller_gateway in out and pc_iface in out,
            "PC route to RockPI",
            first_line(out),
        )
    )
    code, out = capture(
        ["ping", "-c", "1", "-W", "2", addr_host(get(cfg, "supervisor", "pc_addr"))],
        timeout=5,
    )
    checks.append(print_status(code == 0, "PC -> VisionFive ping", first_line(out)))
    code, out = capture(["ping", "-c", "1", "-W", "2", addr_host(ctrl_addr)], timeout=5)
    checks.append(print_status(code == 0, "PC -> RockPI ping", first_line(out)))
    code, out = capture(["ssh", *SSH_AUTO_OPTS, sup, "true"], timeout=5)
    checks.append(print_status(code == 0, "PC -> VisionFive ssh", out))
    code, out = capture(["ssh", *SSH_AUTO_OPTS, ctrl, "true"], timeout=5)
    checks.append(print_status(code == 0, "PC -> RockPI ssh", out))
    ok, out = ssh_check(sup, "sysctl -n net.ipv4.ip_forward", timeout=5)
    checks.append(print_status(ok and out.strip() == "1", "VisionFive forwarding", out))

    print("\n== Time ==")
    ok, skew, out = remote_time_skew(sup)
    checks.append(
        print_status(
            ok and skew is not None and abs(skew) <= 5,
            "VisionFive clock",
            f"{skew:+d}s" if skew is not None else out,
        )
    )
    ok, skew, out = remote_time_skew(ctrl)
    checks.append(
        print_status(
            ok and skew is not None and abs(skew) <= 5,
            "RockPI clock",
            f"{skew:+d}s" if skew is not None else out,
        )
    )

    print("\n== Runtime ==")
    erpc_cmd = (
        f"python3 {shlex.quote(beremiz_stand_dir(cfg) + '/scripts/check_runtime_status.py')} "
        f"{shlex.quote(get(cfg, 'supervisor', 'erpc_url'))}"
    )
    ok, out = ssh_check(sup, erpc_cmd, timeout=10)
    plc_detail = first_line(out) if "PLC Status:" in out else last_line(out)
    checks.append(
        print_status(ok and "PLC Status: Started" in out, "PLC runtime", plc_detail)
    )
    ok, out = ssh_check(
        sup,
        "pgrep -a -f "
        f"{shlex.quote(pgrep_executable_pattern(get(cfg, 'supervisor', 'supervisor_bin')))} "
        "|| true",
        timeout=5,
    )
    checks.append(print_status(ok and bool(out.strip()), "alt-rt-supervisor", first_line(out)))
    ok, out = ssh_check(
        ctrl,
        "pgrep -a -f "
        f"{shlex.quote(pgrep_executable_pattern(get(cfg, 'controller', 'controller_bin')))} "
        "|| true",
        timeout=5,
    )
    checks.append(print_status(ok and bool(out.strip()), "controller-emu", first_line(out)))

    print("\n== Optional Services ==")
    prom_url = get(cfg, "pc", "trace_prometheus_url")
    print_status(http_check(prom_url + "/-/ready"), "trace Prometheus", prom_url, optional=True)
    grafana_addr = get(cfg, "pc", "trace_grafana_addr")
    print_status(http_check(f"http://{grafana_addr}/api/health"), "trace Grafana", f"http://{grafana_addr}", optional=True)
    print_status(
        http_check(f"http://{addr_host(get(cfg, 'supervisor', 'pc_addr'))}:9201/metrics"),
        "VisionFive trace exporter",
        optional=True,
    )
    print_status(
        http_check(f"http://{addr_host(ctrl_addr)}:9201/metrics"),
        "RockPI trace exporter",
        optional=True,
    )

    failures = sum(1 for ok in checks if not ok)
    if failures:
        print(f"\nStatus found {failures} problem(s)")
        return 1
    print("\nStatus OK")
    return 0


def cmd_doctor(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    failures = 0

    rt_tester_dir = Path(get(cfg, "pc", "rt_tester_dir"))
    rt_supervisor_dir = local_rt_supervisor(cfg)
    params = Path(get(cfg, "measurement", "params"))
    arduino_port = Path(get(cfg, "pc", "arduino_port"))

    print("== Local ==")
    checks = [
        print_check(check_local_tool("python3"), "python3 in PATH"),
        print_check(check_local_tool("ssh"), "ssh in PATH"),
        print_check(check_local_tool("scp"), "scp in PATH"),
        print_check(check_local_tool("tar"), "tar in PATH"),
        print_check(check_path(rt_tester_dir), f"rt-tester dir: {rt_tester_dir}"),
        print_check(check_path(rt_supervisor_dir), f"rt-supervisor dir: {rt_supervisor_dir}"),
        print_check(check_path(params), f"measurement params: {params}"),
        print_check(check_path(arduino_port), f"Arduino port: {arduino_port}"),
    ]
    if not check_local_tool("prometheus") and not check_local_tool("/bin/prometheus"):
        checks.append(print_check(False, "prometheus in PATH or /bin/prometheus"))
    else:
        checks.append(print_check(True, "prometheus available"))
    if not check_local_tool("grafana-server") and not check_path(Path("/bin/grafana-server")):
        checks.append(print_check(False, "grafana-server in PATH or /bin/grafana-server"))
    else:
        checks.append(print_check(True, "grafana-server available"))

    print("\n== Profile ==")
    supervisor_board = get(cfg, "supervisor", "board")
    controller_board = get(cfg, "controller", "board")
    checks.extend(
        [
            print_check(supervisor_board in VALID_BOARDS, f"supervisor board: {supervisor_board}"),
            print_check(controller_board in VALID_BOARDS, f"controller board: {controller_board}"),
            print_check("/" in get(cfg, "supervisor", "supervisor_bin"), "supervisor binary path set"),
            print_check("/" in get(cfg, "controller", "controller_bin"), "controller binary path set"),
        ]
    )

    print("\n== Supervisor ==")
    sup = supervisor(cfg)
    ok, out = ssh_check(sup, "true")
    checks.append(print_check(ok, f"ssh {sup}", out))
    if ok:
        for label, path in (
            ("rt-supervisor dir", get(cfg, "supervisor", "rt_supervisor_dir")),
            ("beremiz-stand dir", beremiz_stand_dir(cfg)),
            ("alt-rt-supervisor", get(cfg, "supervisor", "supervisor_bin")),
            ("runtime wrapper", get(cfg, "supervisor", "runtime_wrapper")),
        ):
            path_ok, path_out = ssh_check(sup, f"test -e {path}")
            checks.append(print_check(path_ok, f"{label}: {path}", path_out))

    print("\n== Controller ==")
    ctrl = controller(cfg)
    jump = get(cfg, "controller", "ssh_jump")
    ok, out = ssh_jump_check(jump, ctrl, "true")
    checks.append(print_check(ok, f"ssh {ctrl} via {jump}", out))
    if ok:
        for label, path in (
            ("rt-supervisor dir", get(cfg, "controller", "rt_supervisor_dir")),
            ("controller-emu", get(cfg, "controller", "controller_bin")),
        ):
            path_ok, path_out = ssh_jump_check(jump, ctrl, f"test -e {path}")
            checks.append(print_check(path_ok, f"{label}: {path}", path_out))

    print("\n== Optional Running Services ==")
    prom_url = get(cfg, "pc", "trace_prometheus_url")
    print_check(http_check(prom_url + "/-/ready"), f"trace Prometheus ready: {prom_url}")
    grafana_addr = get(cfg, "pc", "trace_grafana_addr")
    print_check(http_check(f"http://{grafana_addr}/api/health"), f"trace Grafana ready: http://{grafana_addr}")

    failures = sum(1 for ok in checks if not ok)
    if failures:
        print(f"\nDoctor found {failures} problem(s)")
        return 1
    print("\nDoctor passed")
    return 0


def add_measurement_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--groups", type=int, help="override measurement group count")
    parser.add_argument("--interval-us", type=int, help="override Arduino pulse interval")
    parser.add_argument(
        "--measurements-per-group",
        type=int,
        help="override measurements per group",
    )
    parser.add_argument("--arduino-port", help="override Arduino serial port")
    parser.add_argument("--receiver-timeout-sec", type=int, help="override receiver timeout")


def add_dry_run(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print command without running it",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RT supervised stand convenience CLI")
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE),
        help=f"stand profile path (default: {DEFAULT_PROFILE})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    commands = {
        "doctor": cmd_doctor,
        "status": cmd_status,
        "time-check": cmd_time_check,
        "time-restore": cmd_time_restore,
        "network-check": cmd_network_check,
        "network-restore": cmd_network_restore,
        "start": cmd_start,
        "stop": cmd_stop,
        "check": cmd_check,
        "trace-start": cmd_trace_start,
        "trace-stop": cmd_trace_stop,
        "grafana-start": cmd_grafana_start,
        "grafana-stop": cmd_grafana_stop,
    }
    for name, func in commands.items():
        cmd = sub.add_parser(name)
        if name in {"time-check", "time-restore"}:
            cmd.add_argument(
                "--max-skew-sec",
                type=int,
                default=5,
                help="maximum allowed local-to-board clock skew",
            )
        cmd.set_defaults(func=func)

    for name, func, help_text in (
        ("sync-stand", cmd_sync_stand, "sync beremiz-stand workspace to VisionFive"),
        ("build-plc", cmd_build_plc, "build supervised PLC project on VisionFive"),
        (
            "install-runtime-wrapper",
            cmd_install_runtime_wrapper,
            "install Beremiz runtime wrapper on VisionFive",
        ),
        ("start-runtime", cmd_start_runtime, "start Beremiz runtime on VisionFive"),
        ("stop-runtime", cmd_stop_runtime, "stop Beremiz runtime on VisionFive"),
        ("deploy-plc", cmd_deploy_plc, "transfer and run PLC project on runtime"),
        (
            "sync-plc-debug-build",
            cmd_sync_plc_debug_build,
            "copy PLC debug build artifacts back from VisionFive",
        ),
    ):
        cmd = sub.add_parser(name, help=help_text)
        add_dry_run(cmd)
        cmd.set_defaults(func=func)

    smoke = sub.add_parser("test-smoke", help="run non-trace smoke measurement")
    add_measurement_options(smoke)
    smoke.set_defaults(func=cmd_test_smoke)

    trace = sub.add_parser("test-trace", help="run trace smoke measurement")
    add_measurement_options(trace)
    trace.add_argument(
        "--no-trace-start",
        action="store_true",
        help="do not start local trace Prometheus before running smoke",
    )
    trace.set_defaults(func=cmd_test_trace)

    logs = sub.add_parser("collect-logs", help="collect board logs into a local directory")
    logs.add_argument("--output", help="output directory (default: /tmp/rt-stand-logs-*)")
    logs.add_argument("--lines", type=int, default=400, help="tail lines per remote log")
    logs.set_defaults(func=cmd_collect_logs)

    deploy_all = sub.add_parser("deploy-all", help="run full board and PLC deploy sequence")
    deploy_all.add_argument("--dry-run", action="store_true", help="print sequence only")
    deploy_all.add_argument(
        "--no-clean-first",
        action="store_false",
        dest="clean_first",
        default=True,
        help="do not pass --clean-first to rt-supervisor builds",
    )
    deploy_all.add_argument("--skip-rt-supervisor", action="store_true")
    deploy_all.add_argument("--skip-plc", action="store_true")
    deploy_all.add_argument("--skip-smoke", action="store_true")
    deploy_all.add_argument(
        "--trace-smoke",
        action="store_true",
        help="run trace smoke instead of plain smoke",
    )
    deploy_all.add_argument("--groups", type=int, default=1, help="post-deploy smoke groups")
    deploy_all.set_defaults(func=cmd_deploy_all)

    deploy = sub.add_parser("deploy-rt-supervisor", help="sync rt-supervisor sources to boards")
    deploy.add_argument("--supervisor-only", action="store_true", help="only sync VisionFive")
    deploy.add_argument("--controller-only", action="store_true", help="only sync RockPI")
    deploy.add_argument("--dry-run", action="store_true", help="create archive and print actions")
    deploy.set_defaults(func=cmd_deploy_rt_supervisor)

    build = sub.add_parser("build-rt-supervisor", help="build rt-supervisor on boards")
    build.add_argument("--supervisor-only", action="store_true", help="only build VisionFive")
    build.add_argument("--controller-only", action="store_true", help="only build RockPI")
    build.add_argument("--clean-first", action="store_true", help="pass --clean-first to cmake build")
    build.add_argument("--dry-run", action="store_true", help="print remote build commands")
    build.set_defaults(func=cmd_build_rt_supervisor)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        cfg = load_profile(Path(args.profile))
        return int(args.func(cfg, args) or 0)
    except StandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
