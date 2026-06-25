#!/usr/bin/env python3
import argparse
import configparser
import os
import random
import re
import shlex
import shutil
import sqlite3
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


def supervisor_label(cfg: configparser.ConfigParser) -> str:
    return opt(cfg, "supervisor", "label", "supervisor")


def controller_label(cfg: configparser.ConfigParser) -> str:
    return opt(cfg, "controller", "label", "controller")


def supervisor_pinning(cfg: configparser.ConfigParser) -> str:
    return opt(
        cfg,
        "supervisor",
        "pinning_script",
        "/root/pin_visionfive_supervised.sh",
    )


def controller_pinning(cfg: configparser.ConfigParser) -> str:
    return opt(
        cfg,
        "controller",
        "pinning_script",
        "/root/pin_rockpi_controller.sh",
    )


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


def param_value(path: Path, key: str) -> str:
    for line in read_params(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        eq = stripped.split("=", 1)
        if eq[0].strip() == key:
            value = eq[1].split("#", 1)[0].strip()
            return value
    return ""


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
    ses = os.environ.get("RT_TRACE_SESSION_ID", "")
    mpg = os.environ.get("RT_TRACE_MEASUREMENTS_PER_GROUP", "")
    exp = os.environ.get("RT_TRACE_EXPORTERS", "") == "1"
    if ses == "-":
        ses = ""
    _start_stack(cfg, trace_session_id=ses, trace_mpg=mpg, trace_exporters=exp)
    return 0


def cmd_stop(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    ctrl = controller(cfg)
    jump = get(cfg, "controller", "ssh_jump")

    remote_kill_via_jump(jump, ctrl, "controller-emu", "controller-emu")
    remote_kill_pattern_via_jump(jump, ctrl, "trace_exporter.py", "/[t]race_exporter.py/ { print $1 }")

    remote_kill(sup, "alt-rt-supervisor", "alt-rt-supervis")
    remote_kill_pattern(sup, "Beremiz_service.py", "/[B]eremiz_service.py/ { print $1 }")
    remote_kill_pattern(sup, "trace_exporter.py", "/[t]race_exporter.py/ { print $1 }")

    _, out = ssh_check(sup, "rm -f /dev/shm/shmem_input /dev/shm/shmem_output", timeout=5)
    if out:
        print(out)
    return 0


def cmd_check(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    ctrl = controller(cfg)
    jump = get(cfg, "controller", "ssh_jump")

    erpc_cmd = (
        f"python3 {shlex.quote(beremiz_stand_dir(cfg) + '/scripts/check_runtime_status.py')} "
        f"{shlex.quote(get(cfg, 'supervisor', 'erpc_url'))}"
    )

    print("== ERPC runtime ==")
    _, out = ssh_check(sup, erpc_cmd, timeout=10)
    print(out)

    print()
    print(f"== {supervisor_label(cfg)} processes ==")
    _, out = ssh_script(sup, VISIONFIVE_CHECK)
    if out:
        print(out)

    print()
    print(f"== {controller_label(cfg)} processes ==")
    _, out = ssh_jump_script(jump, ctrl, ROCKPI_CHECK)
    if out:
        print(out)

    return 0


_TRACE_PROM_RUNTIME = "/tmp/rt-trace-prometheus-local"


def _local_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _local_stop_pid_file(label: str, pid_file: Path) -> None:
    if not pid_file.is_file():
        print(f"{label}: not running")
        return
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        print(f"{label}: stale pid file")
        pid_file.unlink(missing_ok=True)
        return
    if not _local_pid_alive(pid):
        print(f"{label}: stale pid file")
        pid_file.unlink(missing_ok=True)
        return
    print(f"{label}: stopping pid={pid}")
    try:
        os.kill(pid, 15)
    except OSError:
        pass
    for _ in range(5):
        if not _local_pid_alive(pid):
            print(f"{label}: stopped")
            pid_file.unlink(missing_ok=True)
            return
        time.sleep(1)
    print(f"{label}: killing pid={pid}")
    try:
        os.kill(pid, 9)
    except OSError:
        pass
    pid_file.unlink(missing_ok=True)


def _local_start_tunnel(
    label: str,
    pid_file: Path,
    forward: str,
    ssh_host: str,
    log_file: Path,
) -> None:
    if pid_file.is_file():
        try:
            old = int(pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            old = 0
        if _local_pid_alive(old):
            print(f"{label} tunnel already running pid={old}")
            return
        pid_file.unlink(missing_ok=True)

    with open(log_file, "ab") as lf:
        proc = subprocess.Popen(
            [
                "ssh",
                *SSH_AUTO_OPTS,
                "-N",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                forward,
                ssh_host,
            ],
            stdout=lf,
            stderr=subprocess.STDOUT,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(1)
    if not _local_pid_alive(proc.pid):
        raise StandError(f"{label} tunnel failed; see {log_file}")
    print(f"{label} tunnel pid={proc.pid} forward={forward}")


def cmd_trace_start(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    rt_tester = get(cfg, "pc", "rt_tester_dir")
    prom_addr = get(cfg, "pc", "trace_prometheus_addr")
    runtime = Path(_TRACE_PROM_RUNTIME)
    data_dir = runtime / "data"
    prom_config = Path(rt_tester) / "prometheus" / "trace-prometheus-local-tunnel.yml"
    prom_bin = Path("/bin/prometheus")

    if not prom_bin.is_file():
        raise StandError(f"Prometheus binary not found: {prom_bin}")
    if not prom_config.is_file():
        raise StandError(f"Prometheus config not found: {prom_config}")

    runtime.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    ctrl_addr_host = addr_host(get(cfg, "controller", "addr"))
    vf_forward = "19201:127.0.0.1:9201"
    rp_forward = f"19202:{ctrl_addr_host}:9201"

    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)
    sup_key = sup_label.lower()
    ctrl_key = ctrl_label.lower()

    _local_start_tunnel(
        sup_key,
        runtime / f"{sup_key}-tunnel.pid",
        vf_forward,
        sup,
        runtime / f"{sup_key}.log",
    )
    _local_start_tunnel(
        ctrl_key,
        runtime / f"{ctrl_key}-tunnel.pid",
        rp_forward,
        sup,
        runtime / f"{ctrl_key}.log",
    )

    prom_pid_file = runtime / "prometheus.pid"
    if prom_pid_file.is_file():
        try:
            old = int(prom_pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            old = 0
        if _local_pid_alive(old):
            print(f"trace Prometheus already running pid={old}")
        else:
            prom_pid_file.unlink(missing_ok=True)

    if not prom_pid_file.is_file():
        with open(runtime / "prometheus.log", "ab") as plf:
            proc = subprocess.Popen(
                [
                    str(prom_bin),
                    f"--config.file={prom_config}",
                    f"--storage.tsdb.path={data_dir}",
                    f"--web.listen-address={prom_addr}",
                    "--storage.tsdb.retention.time=2h",
                ],
                stdout=plf,
                stderr=subprocess.STDOUT,
            )
        prom_pid_file.write_text(str(proc.pid), encoding="utf-8")
        time.sleep(2)
        if not _local_pid_alive(proc.pid):
            raise StandError(
                f"trace Prometheus failed; see {runtime / 'prometheus.log'}"
            )
        print(f"trace Prometheus pid={proc.pid} addr={prom_addr}")

    if not http_check(f"http://{prom_addr}/-/ready", timeout=10):
        raise StandError(f"trace Prometheus not ready at {prom_addr}")

    for label, port in (sup_label, "19201"), (ctrl_label, "19202"):
        if not http_check(f"http://127.0.0.1:{port}/metrics", timeout=5):
            print(
                f"trace exporter is not ready at "
                f"http://127.0.0.1:{port}/metrics; normal before smoke starts"
            )

    print(f"TRACE_PROMETHEUS_URL=http://{prom_addr}")
    return 0


def cmd_trace_stop(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    runtime = Path(_TRACE_PROM_RUNTIME)
    sup_key = supervisor_label(cfg).lower()
    ctrl_key = controller_label(cfg).lower()
    _local_stop_pid_file("trace Prometheus", runtime / "prometheus.pid")
    _local_stop_pid_file(
        f"{controller_label(cfg)} tunnel", runtime / f"{ctrl_key}-tunnel.pid"
    )
    _local_stop_pid_file(
        f"{supervisor_label(cfg)} tunnel", runtime / f"{sup_key}-tunnel.pid"
    )
    return 0


_TRACE_GRAFANA_RUNTIME = "/tmp/rt-trace-grafana-local"


def _grafana_pids(data_dir: str) -> list[int]:
    result = subprocess.run(
        ["ps", "-eo", "pid,args"],
        capture_output=True,
        text=True,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        if "grafana" not in line:
            continue
        if data_dir not in line:
            continue
        parts = line.strip().split(None, 1)
        if parts:
            try:
                pids.append(int(parts[0]))
            except ValueError:
                pass
    return pids


def cmd_grafana_start(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    rt_tester = get(cfg, "pc", "rt_tester_dir")
    addr_host, addr_port = get(cfg, "pc", "trace_grafana_addr").rsplit(":", 1)
    runtime = Path(_TRACE_GRAFANA_RUNTIME)
    data_dir = runtime / "data"
    log_dir = runtime / "logs"
    plugin_dir = runtime / "plugins"
    provisioning = Path(rt_tester) / "grafana" / "provisioning"
    pid_file = runtime / "grafana.pid"
    grafana_bin = Path("/bin/grafana-server")
    grafana_home = Path("/usr/share/grafana")

    if not grafana_bin.is_file():
        raise StandError(f"Grafana binary not found: {grafana_bin}")
    if not grafana_home.is_dir():
        raise StandError(f"Grafana home not found: {grafana_home}")
    if not provisioning.is_dir():
        raise StandError(f"Grafana provisioning not found: {provisioning}")

    runtime.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    health_url = f"http://{addr_host}:{addr_port}/api/health"

    if pid_file.is_file():
        try:
            old = int(pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            old = 0
        if _local_pid_alive(old) and http_check(health_url, timeout=2):
            print(f"trace Grafana already running pid={old}")
            print(f"http://{addr_host}:{addr_port}/d/rt-trace-stages")
            return 0
        pid_file.unlink(missing_ok=True)

    stale = _grafana_pids(str(data_dir))
    if stale:
        if http_check(health_url, timeout=2):
            pid_file.write_text(str(stale[0]), encoding="utf-8")
            print(f"trace Grafana already running pid={stale[0]}")
            print(f"http://{addr_host}:{addr_port}/d/rt-trace-stages")
            return 0
        print(f"trace Grafana stale process found; stopping {stale}")
        for p in stale:
            try:
                os.kill(p, 15)
            except OSError:
                pass

    with open(log_dir / "grafana.log", "ab") as glf:
        proc = subprocess.Popen(
            [
                str(grafana_bin),
                f"--homepath={grafana_home}",
                f"cfg:paths.data={data_dir}",
                f"cfg:paths.logs={log_dir}",
                f"cfg:paths.plugins={plugin_dir}",
                f"cfg:paths.provisioning={provisioning}",
                f"cfg:server.http_addr={addr_host}",
                f"cfg:server.http_port={addr_port}",
                "cfg:security.admin_user=admin",
                "cfg:security.admin_password=admin",
                "cfg:auth.anonymous.enabled=true",
                "cfg:auth.anonymous.org_role=Viewer",
            ],
            stdout=glf,
            stderr=subprocess.STDOUT,
        )
    pid_file.write_text(str(proc.pid), encoding="utf-8")

    for _ in range(10):
        if http_check(health_url, timeout=2):
            break
        time.sleep(1)

    live = _grafana_pids(str(data_dir))
    actual_pid = live[0] if live else proc.pid
    if live:
        pid_file.write_text(str(actual_pid), encoding="utf-8")
    if not _local_pid_alive(actual_pid):
        raise StandError(
            f"trace Grafana failed; see {log_dir / 'grafana.log'}"
        )

    if not http_check(health_url, timeout=5):
        raise StandError(
            f"trace Grafana not ready at http://{addr_host}:{addr_port}"
        )

    print(
        f"trace Grafana pid={actual_pid} "
        f"addr={addr_host}:{addr_port}"
    )
    print(f"http://{addr_host}:{addr_port}/d/rt-trace-stages")
    return 0


def cmd_grafana_stop(_cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    runtime = Path(_TRACE_GRAFANA_RUNTIME)
    data_dir = runtime / "data"
    pid_file = runtime / "grafana.pid"

    live_pids: list[int] = []
    if pid_file.is_file():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pid = 0
        if pid and _local_pid_alive(pid):
            live_pids.append(pid)

    if not live_pids:
        live_pids = _grafana_pids(str(data_dir))

    if not live_pids:
        print("trace Grafana: not running")
        pid_file.unlink(missing_ok=True)
        return 0

    pids_str = " ".join(str(p) for p in live_pids)
    print(f"trace Grafana: stopping {pids_str}")
    for pid in live_pids:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
    for _ in range(5):
        alive = [p for p in live_pids if _local_pid_alive(p)]
        if not alive:
            print("trace Grafana: stopped")
            pid_file.unlink(missing_ok=True)
            return 0
        time.sleep(1)
    remaining = " ".join(str(p) for p in alive if _local_pid_alive(p))
    if remaining:
        print(f"trace Grafana: killing {remaining}")
        for pid in live_pids:
            try:
                os.kill(pid, 9)
            except OSError:
                pass
    pid_file.unlink(missing_ok=True)
    return 0


def _run_smoke(
    cfg: configparser.ConfigParser,
    args: argparse.Namespace,
    trace_mode: str,
    params_path: Path,
) -> int:
    params_file = params_path
    smoke_db = param_value(params_file, "db")
    if not smoke_db:
        raise StandError("Smoke params do not define db")
    measurements_per_group = param_value(params_file, "measurements-per-group")
    if not measurements_per_group:
        raise StandError("Smoke params do not define measurements-per-group")

    groups = args.groups or int(get(cfg, "measurement", "groups"))
    if groups < 1:
        raise StandError("SMOKE_GROUPS must be >= 1")

    session_id = random.randint(100000, 999999)
    receiver_dir = (
        Path(get(cfg, "pc", "rt_tester_dir")) / "src" / "pc-receiver"
    )
    arduino_port = args.arduino_port or get(cfg, "pc", "arduino_port")
    receiver_timeout = str(
        args.receiver_timeout_sec
        or opt(cfg, "measurement", "receiver_timeout_sec", "120")
    )

    if trace_mode == "prometheus":
        prom_url = get(cfg, "pc", "trace_prometheus_url")
        if not prom_url:
            raise StandError("TRACE_MODE=prometheus requires TRACE_PROMETHEUS_URL")
        ses = str(session_id)
        exp = True
    else:
        ses = ""
        exp = False

    print("== Start supervised stack ==")
    _start_stack(
        cfg,
        trace_session_id=ses,
        trace_mpg=measurements_per_group,
        trace_exporters=exp,
    )
    print()

    print(f"trace_mode={trace_mode}")

    print("== Check supervised stack ==")
    cmd_check(cfg, argparse.Namespace())

    print()
    print("== Run receiver smoke ==")
    db_path = Path(smoke_db)
    for suffix in ("", "-shm", "-wal"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()

    run(
        [
            sys.executable,
            str(receiver_dir / "receiver.py"),
            "--params",
            str(params_file),
            "--port",
            arduino_port,
            "--session-id",
            str(session_id),
            "--groups",
            str(groups),
            "--start",
            "--exit-on-stop",
        ],
        env={**os.environ, "RT_TESTER_DIR": get(cfg, "pc", "rt_tester_dir")},
    )

    if trace_mode == "prometheus":
        print()
        print("== Import trace metrics ==")
        settle = int(opt(cfg, "measurement", "trace_prometheus_settle_sec", "2"))
        time.sleep(settle)
        run(
            [
                sys.executable,
                str(receiver_dir / "import_trace_metrics.py"),
                smoke_db,
                str(session_id),
                "--prometheus-url",
                get(cfg, "pc", "trace_prometheus_url"),
            ]
        )

    print()
    print("== Smoke database summary ==")
    try:
        with sqlite3.connect(smoke_db) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT session_id, COUNT(*) FROM groups "
                "GROUP BY session_id ORDER BY MAX(id) DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                raise StandError("No groups saved")
            sid, group_count = row

            cur.execute(
                "SELECT COUNT(*), MIN(l.latency_us), AVG(l.latency_us), "
                "MAX(l.latency_us) "
                "FROM latencies l JOIN groups g ON g.id = l.group_id "
                "WHERE g.session_id = ?",
                (sid,),
            )
            latency_count, min_us, avg_us, max_us = cur.fetchone()

            cur.execute(
                "SELECT event_type, details FROM events "
                "WHERE session_id = ? ORDER BY id",
                (sid,),
            )
            events = cur.fetchall()

            cur.execute(
                "SELECT host, stage, COUNT(*), AVG(avg_us), MAX(max_us) "
                "FROM trace_group_metrics "
                "WHERE session_id = ? "
                "GROUP BY host, stage ORDER BY host, stage",
                (sid,),
            )
            trace_rows = cur.fetchall()

        print(f"session={sid}")
        print(f"groups={group_count}")
        print(f"latencies={latency_count}")
        print(f"latency_min_avg_max_us={min_us} / {avg_us:.2f} / {max_us}")
        for event_type, details in events:
            print(f"event={event_type}: {details}")
        for host, stage, tgroups, tavg_us, tmax_us in trace_rows:
            print(
                f"trace={host}/{stage}: groups={tgroups} "
                f"avg_us={tavg_us:.2f} max_us={tmax_us:.2f}"
            )
        if group_count != groups:
            raise StandError(
                f"Expected {groups} groups, saved {group_count}"
            )
    except StandError:
        raise
    except Exception as exc:
        print(f"Summary failed: {exc}")

    return 0


def cmd_test_smoke(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    params, tmp_path = params_for_run(cfg, args)
    try:
        return _run_smoke(cfg, args, "off", params)
    finally:
        cleanup_temp(tmp_path)


def cmd_test_trace(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    params, tmp_path = params_for_run(cfg, args)
    try:
        if not args.no_trace_start:
            cmd_trace_start(cfg, args)
        return _run_smoke(cfg, args, "prometheus", params)
    finally:
        cleanup_temp(tmp_path)


def cmd_trace_summary(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    db_path = args.db or opt(cfg, "measurement", "trace_db", "/tmp/rt-tester-supervised-smoke.db")
    cmd = [
        sys.executable,
        str(
            Path(get(cfg, "pc", "rt_tester_dir"))
            / "src"
            / "pc-receiver"
            / "trace_summary.py"
        ),
        db_path,
    ]
    if args.session_id:
        cmd += ["--session-id", str(args.session_id)]
    if args.host:
        cmd += ["--host", args.host]
    return run(cmd)


def cmd_test_ab(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    repeats = args.ab_repeats
    groups = args.ab_groups
    out_dir = Path(
        args.ab_output
        or f"/tmp/rt-supervised-ab-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"A/B output: {out_dir}")
    print(f"groups per run: {groups}")
    print(f"repeats per mode: {repeats}")

    summary: list[str] = []
    for r in range(1, repeats + 1):
        for mode in ("off", "prometheus"):
            log_file = out_dir / f"{r}-{mode}.log"
            print()
            print(f"== A/B run repeat={r} mode={mode} ==")

            ab_args = argparse.Namespace(
                groups=groups,
                interval_us=args.interval_us,
                measurements_per_group=args.measurements_per_group,
                arduino_port=args.arduino_port,
                receiver_timeout_sec=args.receiver_timeout_sec,
                no_trace_start=False,
            )
            params, tmp_path = params_for_run(cfg, ab_args)
            try:
                with open(log_file, "w", encoding="utf-8") as lf:
                    old_stdout = sys.stdout
                    sys.stdout = lf
                    try:
                        _run_smoke(cfg, ab_args, mode, params)
                    except Exception as exc:
                        print(str(exc), file=sys.stderr)
                        with open(log_file, encoding="utf-8") as rf:
                            print(rf.read())
                        raise
                    finally:
                        sys.stdout = old_stdout
                with open(log_file, encoding="utf-8") as rf:
                    print(rf.read().strip())
            finally:
                cleanup_temp(tmp_path)

            lines: list[str] = []
            try:
                with open(log_file, encoding="utf-8") as rf:
                    for line in rf:
                        line = line.strip()
                        if line.startswith("trace_mode="):
                            tm = line
                        elif line.startswith("session="):
                            ses = line
                        elif line.startswith("groups="):
                            gr = line
                        elif line.startswith("latencies="):
                            lat = line
                        elif line.startswith("latency_min_avg_max_us="):
                            lavg = line
                        elif line.startswith("Imported trace metrics:"):
                            imp = line
                        else:
                            continue
                        lines.append(line)
                parts = [l for l in lines if l]
                summary.append(f"{r}-{mode}: {'; '.join(parts)}")
            except Exception:
                summary.append(f"{r}-{mode}: log error")

    print()
    print("== A/B summary ==")
    for line in summary:
        print(line)

    return 0
    db_path = args.db or opt(cfg, "measurement", "trace_db", "/tmp/rt-tester-supervised-smoke.db")
    cmd = [
        sys.executable,
        str(
            Path(get(cfg, "pc", "rt_tester_dir"))
            / "src"
            / "pc-receiver"
            / "trace_summary.py"
        ),
        db_path,
    ]
    if args.session_id:
        cmd += ["--session-id", str(args.session_id)]
    if not args.all:
        cmd += ["--host", "visionfive"]
    return run(cmd)


def cmd_sync_stand(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    if args.dry_run:
        print(
            "+ sync beremiz-stand workspace to "
            f"{supervisor(cfg)}:{beremiz_stand_dir(cfg)}"
        )
        return 0
    sup = supervisor(cfg)
    remote_dir = beremiz_stand_dir(cfg)
    archive = tempfile.NamedTemporaryFile(
        suffix=".tgz", prefix="beremiz-stand-transfer.", delete=False
    )
    archive.close()
    try:
        run(
            [
                "tar",
                "--exclude=./.git",
                "--exclude=./.deps",
                "--exclude=./beremiz-project/*/build",
                "--exclude=./beremiz-project/*/psk",
                "--exclude=./beremiz-project/*/psk/*",
                "--exclude=__pycache__",
                "-czf",
                archive.name,
                ".",
            ],
            check=False,
        )
        run(
            [
                "scp",
                "-q",
                archive.name,
                f"{sup}:/tmp/beremiz-stand-transfer.tgz",
            ]
        )
        _, out = ssh_check(
            sup,
            f"rm -rf {shlex.quote(remote_dir)} && "
            f"mkdir -p {shlex.quote(remote_dir)} && "
            f"tar -xzf /tmp/beremiz-stand-transfer.tgz -C {shlex.quote(remote_dir)}",
            timeout=120,
        )
        print(f"Synced workspace to {sup}:{remote_dir}")
        if out:
            print(out)
    finally:
        Path(archive.name).unlink(missing_ok=True)
    return 0


def cmd_build_plc(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    remote = beremiz_stand_dir(cfg)
    project = plc_project(cfg)
    cmd = (
        f"cd {shlex.quote(remote)} && "
        f"rm -rf {shlex.quote(project + '/build')} && "
        f"/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py "
        f"--project-home {shlex.quote(project)} build"
    )
    return run_or_dry(["ssh", *SSH_AUTO_OPTS, sup, cmd], args.dry_run)


def cmd_install_runtime_wrapper(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    rtdir = runtime_dir(cfg)
    ip = runtime_bind_ip(cfg)
    port = runtime_port(cfg)
    remote = beremiz_stand_dir(cfg)
    wrapper = f"{rtdir}/start_runtime.sh"
    compat = f"{remote}/scripts/beremiz_runtime_compat_15.py"
    script = (
        "set -eu; "
        f"mkdir -p {shlex.quote(rtdir)}; "
        f"cat > {shlex.quote(wrapper)} <<'WRAPPER_EOF'\n"
        f"#!/bin/sh\n"
        f"set -eu\n"
        f"export PATH=/usr/sbin:/usr/bin:/sbin:/bin\n"
        f"export HOME=/root\n"
        f"cd {shlex.quote(rtdir)}\n"
        f"exec /usr/bin/python3 /usr/share/beremiz/Beremiz_service.py "
        f"-i {shlex.quote(ip)} -p {shlex.quote(port)} -a 1 -x 0 -t 0 -w off "
        f"-e {shlex.quote(compat)} .\n"
        f"WRAPPER_EOF\n"
        f"chmod +x {shlex.quote(wrapper)}; "
        f"ls -l {shlex.quote(wrapper)}"
    )
    if args.dry_run:
        print(f"+ ssh {sup} {script}")
        return 0
    _, out = ssh_check(sup, script, timeout=10)
    print(f"Installed supervised runtime wrapper at {sup}:{wrapper}")
    if out:
        print(out)
    return 0


def cmd_start_runtime(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    rtdir = runtime_dir(cfg)
    ip = runtime_bind_ip(cfg)
    port = runtime_port(cfg)
    remote = beremiz_stand_dir(cfg)
    pidfile = f"{rtdir}/beremiz_service.pid"
    logfile = f"{rtdir}/beremiz_service.log"
    compat = f"{remote}/scripts/beremiz_runtime_compat_15.py"
    script = (
        "set -eu; "
        f"mkdir -p {shlex.quote(rtdir)}; "
        f"if [ -f {shlex.quote(pidfile)} ] && "
        f"kill -0 \"$(cat {shlex.quote(pidfile)})\" 2>/dev/null; then "
        f"echo 'Beremiz runtime already running on {ip}:{port}'; exit 0; fi; "
        f"rm -f {shlex.quote(pidfile)}; "
        f"cd {shlex.quote(rtdir)}; "
        f"EXT_ARGS=; "
        f"if [ -f {shlex.quote(compat)} ]; then "
        f"EXT_ARGS=\"-e {shlex.quote(compat)}\"; fi; "
        f"nohup /usr/bin/python3 /usr/share/beremiz/Beremiz_service.py "
        f"-i {shlex.quote(ip)} -p {shlex.quote(port)} -x 0 -t 0 -w off "
        f"$EXT_ARGS . >{shlex.quote(logfile)} 2>&1 & "
        f"echo $! > {shlex.quote(pidfile)}; "
        f"sleep 2; "
        f"if ! kill -0 \"$(cat {shlex.quote(pidfile)})\" 2>/dev/null; then "
        f"echo 'Beremiz runtime failed to start; log follows:' >&2; "
        f"tail -n 80 {shlex.quote(logfile)} >&2; exit 1; fi; "
        f"grep -q 'Current working directory' {shlex.quote(logfile)} || {{ "
        f"echo 'Beremiz runtime did not report readiness; log follows:' >&2; "
        f"tail -n 80 {shlex.quote(logfile)} >&2; exit 1; }}; "
        f"echo 'Beremiz runtime started on {ip}:{port}'"
    )
    return run_or_dry(["ssh", *SSH_AUTO_OPTS, sup, script], args.dry_run)


def cmd_stop_runtime(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    rtdir = runtime_dir(cfg)
    pidfile = f"{rtdir}/beremiz_service.pid"
    script = (
        "set -eu; "
        f"if [ ! -f {shlex.quote(pidfile)} ]; then "
        f"echo 'Beremiz runtime is not running'; exit 0; fi; "
        f"PID=\"$(cat {shlex.quote(pidfile)})\"; "
        f"if ! kill -0 \"$PID\" 2>/dev/null; then "
        f"rm -f {shlex.quote(pidfile)}; "
        f"echo 'Beremiz runtime is not running'; exit 0; fi; "
        f"kill \"$PID\"; "
        f"for _ in 1 2 3 4 5; do "
        f"if ! kill -0 \"$PID\" 2>/dev/null; then "
        f"rm -f {shlex.quote(pidfile)}; "
        f"echo 'Beremiz runtime stopped'; exit 0; fi; "
        f"sleep 1; done; "
        f"kill -KILL \"$PID\" 2>/dev/null || true; "
        f"rm -f {shlex.quote(pidfile)}; "
        f"echo 'Beremiz runtime killed'"
    )
    return run_or_dry(["ssh", *SSH_AUTO_OPTS, sup, script], args.dry_run)


def cmd_deploy_plc(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    remote = beremiz_stand_dir(cfg)
    uri = get(cfg, "supervisor", "erpc_url")
    project = plc_project(cfg)
    cmd = (
        f"cd {shlex.quote(remote)} && "
        f"/usr/bin/python3 /usr/share/beremiz/Beremiz_cli.py "
        f"--project-home {shlex.quote(project)} "
        f"--uri {shlex.quote(uri)} transfer run"
    )
    return run_or_dry(["ssh", *SSH_AUTO_OPTS, sup, cmd], args.dry_run)


def cmd_sync_plc_debug_build(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    sup = supervisor(cfg)
    remote = beremiz_stand_dir(cfg)
    project = plc_project(cfg)
    local = Path(get(cfg, "supervisor", "beremiz_stand_dir")) / project  # Not actually local — we need repo root
    repo_root = ROOT
    local_project = repo_root / project
    if args.dry_run:
        print(
            f"+ scp -r {sup}:{remote}/{project}/build {local_project}/"
        )
        return 0
    if not local_project.is_dir():
        raise StandError(f"Local project not found: {local_project}")
    run(["rm", "-rf", str(local_project / "build")])
    run(["scp", "-r", f"{sup}:{remote}/{project}/build", str(local_project)])
    print(f"Synced GUI debug build artifacts to {local_project}/build")
    print(f"Open GUI with: beremiz {local_project}")
    return 0


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

    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)
    sup_logs = [
        "/root/alt-rt-supervisor.log",
        f"{runtime_dir(cfg)}/beremiz_service.log",
        "/root/rt-trace-exporter.log",
        "/tmp/rt-supervisor-trace.jsonl",
    ]
    sup_key = sup_label.lower()
    code, out = capture(
        [
            "ssh",
            *SSH_AUTO_OPTS,
            supervisor(cfg),
            remote_log_command(sup_logs, args.lines),
        ],
        timeout=60,
    )
    write_command_output(
        outdir / f"{sup_key}.txt",
        ["ssh", supervisor(cfg), "<snapshot>"],
        code,
        out,
    )

    ctrl_logs = [
        "/root/controller-emu.log",
        "/root/rt-trace-exporter.log",
        "/tmp/controller-emu-trace.jsonl",
    ]
    ctrl_key = ctrl_label.lower()
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    ctrl_command = remote_log_command(ctrl_logs, args.lines)
    remote_cmd = (
        f"ssh {inner_opts} {shlex.quote(controller(cfg))} "
        f"{shlex.quote(ctrl_command)}"
    )
    code, out = capture(
        ["ssh", *SSH_AUTO_OPTS, get(cfg, "controller", "ssh_jump"), remote_cmd],
        timeout=60,
    )
    write_command_output(
        outdir / f"{ctrl_key}.txt",
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
    if jump == host:
        return scp_to(host, local, remote)
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
    if jump == host:
        return ssh_run(host, command)
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    remote_cmd = f"ssh {inner_opts} {shlex.quote(host)} {shlex.quote(command)}"
    return run(["ssh", *SSH_AUTO_OPTS, jump, remote_cmd])


def deploy_archive(host: str, remote_dir: str, archive: Path, jump: str | None = None) -> None:
    assert_safe_remote_dir(remote_dir)
    remote_archive = "/tmp/rt-supervisor-transfer.tgz"
    use_jump = jump and jump != host
    if use_jump:
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
    if use_jump:
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
            sup_label = supervisor_label(cfg)
            ctrl_label = controller_label(cfg)
            print(f"Created archive: {archive}")
            if deploy_supervisor:
                print(
                    f"Would deploy to {sup_label}: "
                    f"{supervisor(cfg)}:{get(cfg, 'supervisor', 'rt_supervisor_dir')}"
                )
            if deploy_controller:
                print(
                    f"Would deploy to {ctrl_label}: "
                    f"{controller(cfg)}:{get(cfg, 'controller', 'rt_supervisor_dir')}"
                )
            return 0
        sup_label = supervisor_label(cfg)
        ctrl_label = controller_label(cfg)
        if deploy_supervisor:
            print(f"== Deploy rt-supervisor to {sup_label} ==")
            deploy_archive(
                supervisor(cfg),
                get(cfg, "supervisor", "rt_supervisor_dir"),
                archive,
            )
        if deploy_controller:
            print(f"== Deploy rt-supervisor to {ctrl_label} ==")
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
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)
    if args.dry_run:
        if build_supervisor:
            print(f"Would run on {sup_label} {supervisor(cfg)}: {supervisor_command}")
        if build_controller:
            print(
                f"Would run on {ctrl_label} "
                f"{controller(cfg)} via {get(cfg, 'controller', 'ssh_jump')}: "
                f"{controller_command}"
            )
        return 0
    if build_supervisor:
        print(f"== Build alt-rt-supervisor on {sup_label} ==")
        ssh_run(supervisor(cfg), supervisor_command)
    if build_controller:
        print(f"== Build controller-emu on {ctrl_label} ==")
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


def ssh_script(host: str, script: str, timeout: int = 30) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            ["ssh", *SSH_AUTO_OPTS, host, "sh -s"],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode == 0, completed.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        return False, (exc.stdout or "timeout").strip()


def ssh_jump_script(
    jump: str,
    host: str,
    script: str,
    timeout: int = 30,
    shell_args: list[str] | None = None,
) -> tuple[bool, str]:
    try:
        if jump == host:
            if shell_args:
                return _ssh_script_args(host, script, shell_args, timeout=timeout)
            return ssh_script(host, script, timeout=timeout)
        inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
        args_suffix = ""
        if shell_args:
            args_suffix = " -- " + " ".join(shlex.quote(a) for a in shell_args)
        completed = subprocess.run(
            [
                "ssh",
                *SSH_AUTO_OPTS,
                jump,
                f"cat | ssh {inner_opts} {shlex.quote(host)} sh -s{args_suffix}",
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode == 0, completed.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        return False, (exc.stdout or "timeout").strip()


def ssh_jump_check(jump: str, host: str, command: str, timeout: int = 10) -> tuple[bool, str]:
    if jump == host:
        return ssh_check(host, command, timeout=timeout)
    inner_opts = " ".join(shlex.quote(part) for part in SSH_AUTO_OPTS)
    remote_cmd = f"ssh {inner_opts} {shlex.quote(host)} {shlex.quote(command)}"
    code, out = capture(["ssh", *SSH_AUTO_OPTS, jump, remote_cmd], timeout=timeout)
    return code == 0, out


KILL_SCRIPT = """\
kill_pids()
{
    label=$1
    pids=$2
    if [ -z "$pids" ]; then
        echo "$label: not running"
        return 0
    fi
    echo "$label: stopping $pids"
    kill $pids 2>/dev/null || true
    i=0
    while [ $i -lt 5 ]; do
        alive=
        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then
                alive="$alive $pid"
            fi
        done
        if [ -z "$alive" ]; then
            echo "$label: stopped"
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    echo "$label: killing$alive"
    kill -KILL $alive 2>/dev/null || true
}
"""


def _kill_cmd(label: str, pgrep_name: str | None = None, awk_pattern: str | None = None) -> str:
    if pgrep_name:
        return (
            f"pids=$(pgrep -x {shlex.quote(pgrep_name)} "
            f"2>/dev/null | tr '\\n' ' ' || true)\n"
            f"kill_pids {shlex.quote(label)} \"$pids\""
        )
    if awk_pattern:
        return (
            f"pids=$(ps -eo pid,args | awk {shlex.quote(awk_pattern)} "
            f"| tr '\\n' ' ')\n"
            f"kill_pids {shlex.quote(label)} \"$pids\""
        )
    raise StandError("need pgrep_name or awk_pattern")


def remote_kill(host: str, label: str, pgrep_name: str, timeout: int = 20) -> None:
    _, out = ssh_script(host, KILL_SCRIPT + _kill_cmd(label, pgrep_name=pgrep_name), timeout=timeout)
    if out:
        print(out)


def remote_kill_via_jump(
    jump: str,
    host: str,
    label: str,
    pgrep_name: str,
    timeout: int = 20,
) -> None:
    _, out = ssh_jump_script(jump, host, KILL_SCRIPT + _kill_cmd(label, pgrep_name=pgrep_name), timeout=timeout)
    if out:
        print(out)


def remote_kill_pattern(
    host: str,
    label: str,
    awk_pattern: str,
    timeout: int = 20,
) -> None:
    _, out = ssh_script(host, KILL_SCRIPT + _kill_cmd(label, awk_pattern=awk_pattern), timeout=timeout)
    if out:
        print(out)


def remote_kill_pattern_via_jump(
    jump: str,
    host: str,
    label: str,
    awk_pattern: str,
    timeout: int = 20,
) -> None:
    _, out = ssh_jump_script(jump, host, KILL_SCRIPT + _kill_cmd(label, awk_pattern=awk_pattern), timeout=timeout)
    if out:
        print(out)


VISIONFIVE_START = """\
set -eu
SUPERVISOR_BIN=$1
RUNTIME_WRAPPER=$2
INTERFACE=$3
TIMEOUT_US=$4
TRACE_SESSION_ID=$5
TRACE_PATH=$6
TRACE_EXPORTERS=${7:-0}

if [ "$TRACE_SESSION_ID" = - ]; then
    TRACE_SESSION_ID=
fi

: > /root/alt-rt-supervisor.log
if [ -n "$TRACE_SESSION_ID" ]; then
    : > "$TRACE_PATH"
    if [ "$TRACE_EXPORTERS" = 1 ] && [ -x /root/rt-supervisor/scripts/trace_exporter.py ]; then
        nohup /root/rt-supervisor/scripts/trace_exporter.py \
            --listen 0.0.0.0 --port 9201 "$TRACE_PATH" \
            >/root/rt-trace-exporter.log 2>&1 &
        echo "visionfive trace_exporter pid=$!"
    fi
    RT_TRACE_PATH="$TRACE_PATH" nohup /root/rt-supervisor/scripts/run_supervisor.sh \
        "$INTERFACE" "$TIMEOUT_US" "$RUNTIME_WRAPPER" "$SUPERVISOR_BIN" \
        >/root/alt-rt-supervisor.log 2>&1 &
else
    nohup /root/rt-supervisor/scripts/run_supervisor.sh \
        "$INTERFACE" "$TIMEOUT_US" "$RUNTIME_WRAPPER" "$SUPERVISOR_BIN" \
        >/root/alt-rt-supervisor.log 2>&1 &
fi
echo "alt-rt-supervisor pid=$!"
"""

ROCKPI_START = """\
set -eu
CONTROLLER_BIN=$1
INTERFACE=$2
TRACE_SESSION_ID=$3
TRACE_MPG=$4
TRACE_PATH=$5
TRACE_EXPORTERS=${6:-0}

if [ "$TRACE_SESSION_ID" = - ]; then
    TRACE_SESSION_ID=
fi
if [ "$TRACE_MPG" = - ]; then
    TRACE_MPG=
fi

: > /root/controller-emu.log
if [ -n "$TRACE_SESSION_ID" ] && [ -n "$TRACE_MPG" ]; then
    : > "$TRACE_PATH"
    if [ "$TRACE_EXPORTERS" = 1 ] && [ -x /root/rt-supervisor/scripts/trace_exporter.py ]; then
        nohup /root/rt-supervisor/scripts/trace_exporter.py \
            --listen 0.0.0.0 --port 9201 "$TRACE_PATH" \
            >/root/rt-trace-exporter.log 2>&1 &
        echo "rockpi trace_exporter pid=$!"
    fi
    RT_TRACE_PATH="$TRACE_PATH" \
    RT_TRACE_SESSION_ID="$TRACE_SESSION_ID" \
    RT_TRACE_MEASUREMENTS_PER_GROUP="$TRACE_MPG" \
        nohup /root/rt-supervisor/scripts/run_controller.sh \
        "$INTERFACE" "$CONTROLLER_BIN" >/root/controller-emu.log 2>&1 &
else
    nohup /root/rt-supervisor/scripts/run_controller.sh \
        "$INTERFACE" "$CONTROLLER_BIN" >/root/controller-emu.log 2>&1 &
fi
echo "controller-emu pid=$!"
"""

VISIONFIVE_CHECK = """\
set -eu
supervisor_pids=$(pgrep -x alt-rt-supervis 2>/dev/null | tr '\\n' ' ' || true)
runtime_pids=$(ps -eo pid,args | awk '/[B]eremiz_service.py/ { print $1 }' | tr '\\n' ' ')

print_processes()
{
    label=$1
    pids=$2
    if [ -z "$pids" ]; then
        echo "$label: missing"
        return 1
    fi
    pid_csv=$(printf '%s\\n' $pids | paste -sd, -)
    echo "$label: $pids"
    ps -o pid,cls,rtprio,pri,psr,comm,args -p "$pid_csv"
    ps -L -o pid,tid,cls,rtprio,pri,psr,comm -p "$pid_csv"
    for pid in $pids; do
        awk '/Cpus_allowed_list/ { print "pid " pid " Cpus_allowed_list=" $2 }' \
            pid="$pid" "/proc/$pid/status"
        for status in /proc/$pid/task/*/status; do
            [ -e "$status" ] || continue
            tid=${status%/status}
            tid=${tid##*/}
            awk '/Cpus_allowed_list/ { print "tid " tid " Cpus_allowed_list=" $2 }' \
                tid="$tid" "$status"
        done
    done
}

failed=0
print_processes "alt-rt-supervisor" "$supervisor_pids" || failed=1
print_processes "Beremiz_service.py" "$runtime_pids" || failed=1

for slot in /dev/shm/shmem_input /dev/shm/shmem_output; do
    if [ -e "$slot" ]; then
        ls -l "$slot"
    else
        echo "$slot: missing"
        failed=1
    fi
done

exit "$failed"
"""

ROCKPI_CHECK = """\
set -eu
pids=$(pgrep -x controller-emu 2>/dev/null | tr '\\n' ' ' || true)
if [ -z "$pids" ]; then
    echo "controller-emu: missing"
    exit 1
fi
pid_csv=$(printf '%s\\n' $pids | paste -sd, -)
echo "controller-emu: $pids"
ps -o pid,cls,rtprio,pri,psr,comm,args -p "$pid_csv"
ps -L -o pid,tid,cls,rtprio,pri,psr,comm -p "$pid_csv"
for pid in $pids; do
    awk '/Cpus_allowed_list/ { print "pid " pid " Cpus_allowed_list=" $2 }' \
        pid="$pid" "/proc/$pid/status"
    for status in /proc/$pid/task/*/status; do
        [ -e "$status" ] || continue
        tid=${status%/status}
        tid=${tid##*/}
        awk '/Cpus_allowed_list/ { print "tid " tid " Cpus_allowed_list=" $2 }' \
            tid="$tid" "$status"
    done
done
"""


def _ssh_script_args(
    host: str,
    script: str,
    shell_args: list[str],
    timeout: int = 30,
) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            [
                "ssh",
                *SSH_AUTO_OPTS,
                host,
                "sh -s -- " + " ".join(shlex.quote(a) for a in shell_args),
            ],
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode == 0, completed.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        return False, (exc.stdout or "timeout").strip()


def _start_stack(
    cfg: configparser.ConfigParser,
    trace_session_id: str = "",
    trace_mpg: str = "",
    trace_exporters: bool = False,
) -> None:
    cmd_stop(cfg, argparse.Namespace())

    sup = supervisor(cfg)
    ctrl = controller(cfg)
    jump = get(cfg, "controller", "ssh_jump")
    supervisor_bin = get(cfg, "supervisor", "supervisor_bin")
    controller_bin = get(cfg, "controller", "controller_bin")
    runtime_wrapper = get(cfg, "supervisor", "runtime_wrapper")
    iface = get(cfg, "supervisor", "iface")

    ses = trace_session_id or "-"
    mpg = trace_mpg or "-"
    exp = "1" if trace_exporters else "0"
    timeout_us = os.environ.get("TIMEOUT_US", "5000000")
    trace_sup = opt(cfg, "supervisor", "trace_supervisor_path", "/tmp/rt-supervisor-trace.jsonl")
    trace_ctrl = opt(cfg, "controller", "trace_controller_path", "/tmp/controller-emu-trace.jsonl")

    _, out = _ssh_script_args(
        sup,
        VISIONFIVE_START,
        [supervisor_bin, runtime_wrapper, iface, timeout_us, ses, trace_sup, exp],
    )
    if out:
        print(out)

    _, out = ssh_jump_script(
        jump,
        ctrl,
        ROCKPI_START,
        shell_args=[controller_bin, iface, ses, mpg, trace_ctrl, exp],
    )
    if out:
        print(out)

    time.sleep(4)
    _, out = ssh_check(sup, supervisor_pinning(cfg), timeout=10)
    if out:
        print(out)
    _, out = ssh_jump_check(jump, ctrl, controller_pinning(cfg), timeout=10)
    if out:
        print(out)


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
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)

    print("== Local ==")
    print(datetime.now().astimezone().isoformat())

    print(f"\n== {sup_label} ==")
    ok, skew, out = remote_time_skew(supervisor(cfg))
    if ok and skew is not None:
        checks.append(
            print_check(abs(skew) <= max_skew, f"skew <= {max_skew}s", f"{skew:+d}s")
        )
    else:
        print(out)
        checks.append(print_check(False, f"read {sup_label} time"))

    print(f"\n== {ctrl_label} ==")
    ok, skew, out = remote_time_skew_via_jump(get(cfg, "controller", "ssh_jump"), controller(cfg))
    if ok and skew is not None:
        checks.append(
            print_check(abs(skew) <= max_skew, f"skew <= {max_skew}s", f"{skew:+d}s")
        )
    else:
        print(out)
        checks.append(print_check(False, f"read {ctrl_label} time"))

    failures = sum(1 for ok in checks if not ok)
    if failures:
        print(f"\nTime check found {failures} problem(s)")
        return 1
    print("\nTime check passed")
    return 0


def cmd_time_restore(cfg: configparser.ConfigParser, args: argparse.Namespace) -> int:
    epoch = int(time.time())
    checks: list[bool] = []
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)

    print(f"== Set board clocks to PC epoch {epoch} ==")

    print(f"\n== {sup_label} ==")
    ok, out = set_remote_time(supervisor(cfg), epoch)
    print(out)
    checks.append(print_check(ok, f"set {sup_label} time"))

    print(f"\n== {ctrl_label} ==")
    ok, out = set_remote_time_via_jump(get(cfg, "controller", "ssh_jump"), controller(cfg), epoch)
    print(out)
    checks.append(print_check(ok, f"set {ctrl_label} time"))

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
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)
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

    print(f"\n== PC -> {sup_label} ==")
    code, out = capture(["ping", "-c", "3", "-W", "2", addr_host(sup_pc_addr)], timeout=10)
    checks.append(print_check(code == 0, f"ping {addr_host(sup_pc_addr)}", out.splitlines()[-1] if out else ""))
    ok, out = ssh_check(sup, f"ip -br addr show {sup_pc_iface}; ip -br addr show {sup_ctrl_iface}")
    print(out)
    checks.append(print_check(ok and contains_addr(out, sup_pc_addr), f"{sup_label} {sup_pc_iface} has {sup_pc_addr}"))
    checks.append(print_check(ok and contains_addr(out, sup_ctrl_addr), f"{sup_label} {sup_ctrl_iface} has {sup_ctrl_addr}"))
    ok, out = ssh_check(sup, "sysctl -n net.ipv4.ip_forward")
    checks.append(print_check(ok and out.strip() == "1", f"{sup_label} IPv4 forwarding enabled", out))

    print(f"\n== {sup_label} -> {ctrl_label} ==")
    ok, out = ssh_jump_check(jump, ctrl, f"ip -br addr show {ctrl_iface}")
    print(out)
    checks.append(print_check(ok and contains_addr(out, ctrl_addr), f"{ctrl_label} {ctrl_iface} has {ctrl_addr}"))
    ok_route, route_out = ssh_jump_check(jump, ctrl, f"ip route get {addr_host(pc_addr)}")
    print(route_out)
    checks.append(
        print_check(
            ok_route and ctrl_pc_gateway in route_out,
            f"{ctrl_label} route {ctrl_pc_route} via {ctrl_pc_gateway}",
        )
    )
    ok, out = ssh_check(sup, f"ping -c 3 -W 2 {addr_host(ctrl_addr)}")
    checks.append(print_check(ok, f"{sup_label} ping {ctrl_label} {addr_host(ctrl_addr)}", out.splitlines()[-1] if out else ""))

    print(f"\n== PC -> {ctrl_label} Direct ==")
    code, out = capture(["ping", "-c", "3", "-W", "2", addr_host(ctrl_addr)], timeout=10)
    checks.append(print_check(code == 0, f"PC ping {ctrl_label} {addr_host(ctrl_addr)}", out.splitlines()[-1] if out else ""))
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
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)
    ok, out = ssh_check(sup, "true", timeout=5)
    if not ok:
        print(f"\n{sup_label} is still unreachable over SSH after PC Ethernet restore.")
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

    print(f"\n== Restore {sup_label} Interfaces ==")
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
            raise StandError(f"failed to restore {sup_label} {iface}")

    ok, out = remote_enable_ip_forward(
        sup,
        opt(cfg, "supervisor", "enable_ip_forward", "yes").lower() in {"1", "yes", "true", "on"},
    )
    print(out)
    if not ok:
        raise StandError(f"failed to enable {sup_label} IPv4 forwarding")

    print(f"\n== Restore {ctrl_label} Interface If Reachable ==")
    ok, out = ssh_jump_check(get(cfg, "controller", "ssh_jump"), controller(cfg), "true", timeout=5)
    if not ok:
        print(f"{ctrl_label} is not reachable via {sup_label}; skipping {ctrl_label} restore")
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
        raise StandError(f"failed to restore {ctrl_label} interface")

    ok, out = remote_restore_route_via_jump(
        get(cfg, "controller", "ssh_jump"),
        controller(cfg),
        get(cfg, "controller", "connection"),
        get(cfg, "controller", "pc_route"),
        get(cfg, "controller", "pc_gateway"),
    )
    print(out)
    if not ok:
        raise StandError(f"failed to restore {ctrl_label} reverse route")

    ok, out = install_controller_ssh_key(cfg)
    if ok:
        print(f"Installed PC SSH public key on {ctrl_label}")
    else:
        print(f"{ctrl_label} SSH key install skipped/failed: {out}")

    return cmd_network_check(cfg, _args)


def cmd_status(cfg: configparser.ConfigParser, _args: argparse.Namespace) -> int:
    checks: list[bool] = []
    sup = supervisor(cfg)
    ctrl = controller(cfg)
    ctrl_addr = get(cfg, "controller", "addr")
    pc_controller_gateway = get(cfg, "pc", "controller_gateway")
    pc_iface = get(cfg, "pc", "ethernet_iface")
    sup_label = supervisor_label(cfg)
    ctrl_label = controller_label(cfg)

    print("== Network ==")
    code, out = capture(["ip", "route", "get", addr_host(ctrl_addr)], timeout=5)
    checks.append(
        print_status(
            code == 0 and pc_controller_gateway in out and pc_iface in out,
            "PC route to controller",
            first_line(out),
        )
    )
    code, out = capture(
        ["ping", "-c", "1", "-W", "2", addr_host(get(cfg, "supervisor", "pc_addr"))],
        timeout=5,
    )
    checks.append(print_status(code == 0, f"PC -> {sup_label} ping", first_line(out)))
    code, out = capture(["ping", "-c", "1", "-W", "2", addr_host(ctrl_addr)], timeout=5)
    checks.append(print_status(code == 0, f"PC -> {ctrl_label} ping", first_line(out)))
    code, out = capture(["ssh", *SSH_AUTO_OPTS, sup, "true"], timeout=5)
    checks.append(print_status(code == 0, f"PC -> {sup_label} ssh", out))
    code, out = capture(["ssh", *SSH_AUTO_OPTS, ctrl, "true"], timeout=5)
    checks.append(print_status(code == 0, f"PC -> {ctrl_label} ssh", out))
    if opt(cfg, "supervisor", "enable_ip_forward", "").lower() in {"1", "yes", "true", "on"}:
        ok, out = ssh_check(sup, "sysctl -n net.ipv4.ip_forward", timeout=5)
        checks.append(print_status(ok and out.strip() == "1", f"{sup_label} forwarding", out))

    print("\n== Time ==")
    ok, skew, out = remote_time_skew(sup)
    checks.append(
        print_status(
            ok and skew is not None and abs(skew) <= 5,
            f"{sup_label} clock",
            f"{skew:+d}s" if skew is not None else out,
        )
    )
    ok, skew, out = remote_time_skew(ctrl)
    checks.append(
        print_status(
            ok and skew is not None and abs(skew) <= 5,
            f"{ctrl_label} clock",
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
        f"{sup_label} trace exporter",
        optional=True,
    )
    print_status(
        http_check(f"http://{addr_host(ctrl_addr)}:9201/metrics"),
        f"{ctrl_label} trace exporter",
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
        ("sync-stand", cmd_sync_stand, "sync beremiz-stand workspace to supervisor"),
        ("build-plc", cmd_build_plc, "build supervised PLC project on supervisor"),
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
            "copy PLC debug build artifacts back from supervisor",
        ),
    ):
        cmd = sub.add_parser(name, help=help_text)
        add_dry_run(cmd)
        cmd.set_defaults(func=func)

    smoke = sub.add_parser("test-smoke", help="run non-trace smoke measurement")
    add_measurement_options(smoke)
    smoke.set_defaults(func=cmd_test_smoke)

    trace_summary = sub.add_parser("trace-summary", help="print trace stage breakdown")
    trace_summary.add_argument("--db", help="path to smoke SQLite database")
    trace_summary.add_argument("--session-id", type=int, help="session ID to summarize (default: latest)")
    trace_summary.add_argument(
        "--host",
        help="filter by host name (default: all hosts)",
    )
    trace_summary.set_defaults(func=cmd_trace_summary)

    trace = sub.add_parser("test-trace", help="run trace smoke measurement")
    add_measurement_options(trace)
    trace.add_argument(
        "--no-trace-start",
        action="store_true",
        help="do not start local trace Prometheus before running smoke",
    )
    trace.set_defaults(func=cmd_test_trace)

    ab_test = sub.add_parser("test-ab", help="run A/B overhead comparison (off, prometheus)")
    add_measurement_options(ab_test)
    ab_test.add_argument("--ab-repeats", type=int, default=1, help="repeats per mode")
    ab_test.add_argument("--ab-groups", type=int, default=2, help="groups per repeat")
    ab_test.add_argument("--ab-output", help="output directory (default: /tmp/rt-supervised-ab-*)")
    ab_test.set_defaults(func=cmd_test_ab)

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
    deploy.add_argument("--supervisor-only", action="store_true", help="only sync/deploy to supervisor")
    deploy.add_argument("--controller-only", action="store_true", help="only sync/deploy to controller")
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
