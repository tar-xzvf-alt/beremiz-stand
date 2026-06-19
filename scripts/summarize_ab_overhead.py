#!/usr/bin/env python3
import argparse
import re
from dataclasses import dataclass
from pathlib import Path


RUN_RE = re.compile(r"^(?P<repeat>\d+)-(?P<mode>[a-z]+)\.log$")
SESSION_RE = re.compile(r"^session=(?P<session>\d+)$", re.MULTILINE)
GROUPS_RE = re.compile(r"^groups=(?P<groups>\d+)$", re.MULTILINE)
LATENCIES_RE = re.compile(r"^latencies=(?P<latencies>\d+)$", re.MULTILINE)
LATENCY_RE = re.compile(
    r"^latency_min_avg_max_us=(?P<min>\d+) / (?P<avg>[0-9.]+) / (?P<max>\d+)$",
    re.MULTILINE,
)
IMPORTED_RE = re.compile(r"^Imported trace metrics: (?P<count>\d+)$", re.MULTILINE)
TRACE_RE = re.compile(
    r"^trace=(?P<host>[^/]+)/(?P<stage>[^:]+): groups=(?P<groups>\d+) "
    r"avg_us=(?P<avg>[0-9.]+) max_us=(?P<max>[0-9.]+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class Run:
    repeat: int
    mode: str
    session: str
    groups: int
    latencies: int
    min_us: int
    avg_us: float
    max_us: int
    imported: int | None


def required(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"missing {label}")
    return match


def parse_run(path: Path) -> tuple[Run, list[tuple[str, str, int, float, float]]]:
    name_match = RUN_RE.match(path.name)
    if name_match is None:
        raise ValueError(f"unexpected log name: {path.name}")

    text = path.read_text(encoding="utf-8")
    latency_match = required(LATENCY_RE, text, "latency summary")
    imported_match = IMPORTED_RE.search(text)

    run = Run(
        repeat=int(name_match.group("repeat")),
        mode=name_match.group("mode"),
        session=required(SESSION_RE, text, "session").group("session"),
        groups=int(required(GROUPS_RE, text, "groups").group("groups")),
        latencies=int(required(LATENCIES_RE, text, "latencies").group("latencies")),
        min_us=int(latency_match.group("min")),
        avg_us=float(latency_match.group("avg")),
        max_us=int(latency_match.group("max")),
        imported=int(imported_match.group("count")) if imported_match else None,
    )

    traces = [
        (
            match.group("host"),
            match.group("stage"),
            int(match.group("groups")),
            float(match.group("avg")),
            float(match.group("max")),
        )
        for match in TRACE_RE.finditer(text)
    ]
    return run, traces


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def print_runs(runs: list[Run]) -> None:
    print("Per-run latency:")
    print("repeat mode       session groups latencies min_us avg_us  max_us imported")
    for run in runs:
        imported = "-" if run.imported is None else str(run.imported)
        print(
            f"{run.repeat:>6} {run.mode:<10} {run.session:<7} "
            f"{run.groups:>6} {run.latencies:>9} {run.min_us:>6} "
            f"{run.avg_us:>7.2f} {run.max_us:>7} {imported:>8}"
        )


def mode_key(mode: str) -> tuple[int, str]:
    order = {"off": 0, "jsonl": 1, "prometheus": 2}
    return (order.get(mode, 99), mode)


def print_mode_summary(runs: list[Run]) -> None:
    print()
    print("Mode summary:")
    print("mode       runs avg_latency_us min_avg_us max_avg_us mean_max_us max_us")
    modes = sorted({run.mode for run in runs}, key=mode_key)
    for mode in modes:
        mode_runs = [run for run in runs if run.mode == mode]
        avg_values = [run.avg_us for run in mode_runs]
        max_values = [float(run.max_us) for run in mode_runs]
        print(
            f"{mode:<10} {len(mode_runs):>4} {mean(avg_values):>14.2f} "
            f"{min(avg_values):>10.2f} {max(avg_values):>10.2f} "
            f"{mean(max_values):>11.2f} {max(max_values):>6.0f}"
        )


def print_trace_summary(traces: list[tuple[str, str, int, float, float]]) -> None:
    if not traces:
        return

    print()
    print("Trace summary from prometheus runs:")
    print("host       stage              runs mean_avg_us max_us")
    keys = sorted({(host, stage) for host, stage, _, _, _ in traces})
    for host, stage in keys:
        rows = [row for row in traces if row[0] == host and row[1] == stage]
        avg_values = [row[3] for row in rows]
        max_values = [row[4] for row in rows]
        print(
            f"{host:<10} {stage:<18} {len(rows):>4} "
            f"{mean(avg_values):>11.2f} {max(max_values):>6.0f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize run_supervised_ab_overhead.sh logs."
    )
    parser.add_argument("log_dir", type=Path)
    args = parser.parse_args()

    logs = sorted(args.log_dir.glob("*-*.log"))
    if not logs:
        raise SystemExit(f"no A/B logs found in {args.log_dir}")

    runs: list[Run] = []
    traces: list[tuple[str, str, int, float, float]] = []
    for path in logs:
        run, run_traces = parse_run(path)
        runs.append(run)
        traces.extend(run_traces)

    runs.sort(key=lambda run: (run.repeat, mode_key(run.mode)))
    print_runs(runs)
    print_mode_summary(runs)
    print_trace_summary(traces)


if __name__ == "__main__":
    main()
