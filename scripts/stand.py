#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from _lib import StandError, load_profile, DEFAULT_PROFILE
from _cmd import (
    cmd_doctor, cmd_status,
    cmd_time_check, cmd_time_restore,
    cmd_network_check, cmd_network_restore,
    cmd_start, cmd_stop, cmd_check,
    cmd_trace_start, cmd_trace_stop,
    cmd_grafana_start, cmd_grafana_stop,
    cmd_sync_stand, cmd_build_plc, cmd_install_runtime_wrapper,
    cmd_start_runtime, cmd_stop_runtime, cmd_deploy_plc,
    cmd_sync_plc_debug_build, cmd_deploy_all, cmd_collect_logs,
    cmd_deploy_rt_supervisor, cmd_build_rt_supervisor,
    cmd_test_smoke, cmd_test_trace, cmd_test_ab, cmd_trace_summary,
)

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
    build.add_argument("--supervisor-only", action="store_true", help="only build supervisor")
    build.add_argument("--controller-only", action="store_true", help="only build controller")
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
