#!/usr/bin/python3
import argparse
import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENDER_PATH = ROOT / "raw-ethernet" / "send_raw_packet.py"


CASES = (
	("LOW", 400, 1, 0),
	("HIGH", 600, 0, 1),
	("LOW-AGAIN", 250, 1, 0),
)


def load_sender():
	spec = importlib.util.spec_from_file_location("send_raw_packet", SENDER_PATH)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def run_ssh(target, command):
	ssh_command = ["ssh", target, command]
	sudo_user = os.environ.get("SUDO_USER")
	if os.geteuid() == 0 and sudo_user and sudo_user != "root":
		ssh_command = ["sudo", "-u", sudo_user] + ssh_command
	return subprocess.run(
		ssh_command,
		check=False,
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
	)


def read_runtime_log(target, log_path):
	result = run_ssh(target, f"tail -n 240 {log_path}")
	if result.returncode != 0:
		raise RuntimeError(
			f"failed to read runtime log via ssh: {result.stderr.strip()}"
		)
	return result.stdout


def wait_for_line(args, expected_line):
	deadline = time.monotonic() + args.timeout
	last_log = ""
	while time.monotonic() < deadline:
		last_log = read_runtime_log(args.target, args.runtime_log)
		if expected_line in last_log:
			return
		time.sleep(args.interval)
	raise TimeoutError(
		f"runtime log did not contain expected line:\n{expected_line}\n"
		f"last log tail:\n{last_log}"
	)


def parse_args():
	parser = argparse.ArgumentParser(
		description="Send raw Ethernet packets and verify direct c_ext PLC output."
	)
	parser.add_argument("--interface", "-i", default="enp2s0")
	parser.add_argument("--target", default="root@10.42.0.211")
	parser.add_argument(
		"--runtime-log",
		default="/root/beremiz-runtime/direct-raw-plc/beremiz_service.log",
	)
	parser.add_argument("--threshold", type=int, default=500)
	parser.add_argument("--sequence-base", type=int, default=None)
	parser.add_argument("--timeout", type=float, default=5.0)
	parser.add_argument("--interval", type=float, default=0.1)
	return parser.parse_args()


def main():
	args = parse_args()
	sender = load_sender()
	sequence_base = args.sequence_base
	if sequence_base is None:
		sequence_base = int(time.time()) & 0xFFFF0000

	try:
		for index, (label, sensor, forced_output, expected_output) in enumerate(CASES, 1):
			sequence = sequence_base + index
			sent = sender.send_frame(
				args.interface,
				sequence,
				sensor,
				args.threshold,
				forced_output,
			)
			expected_line = (
				f"direct raw plc seq={sequence} sensor={sensor} "
				f"threshold={args.threshold} forced_output={forced_output} "
				f"output={expected_output}"
			)
			wait_for_line(args, expected_line)
			print(
				f"{label}: sent={sent} sequence={sequence} sensor={sensor} "
				f"threshold={args.threshold} forced_output={forced_output} "
				f"output={expected_output}"
			)
	except PermissionError as exc:
		print(f"raw socket permission denied: {exc}", file=sys.stderr)
		print("run this demo as root or grant CAP_NET_RAW", file=sys.stderr)
		return 1
	except Exception as exc:
		print(f"direct raw Ethernet demo failed: {exc}", file=sys.stderr)
		return 1

	print("direct raw Ethernet demo passed")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
