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
DEFAULT_PROFILE = Path(
    os.environ.get(
        "BEREMIZ_STAND_PROFILE",
        ROOT / "profiles" / "visionfive-rockpi.conf",
    )
)
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
VALID_CONTROLLER_BOARDS = (VALID_BOARDS - {"starfive"}) | {"visionfive2"}
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
        get(cfg, "supervisor", "pc_addr").split("/", 1)[0],
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
