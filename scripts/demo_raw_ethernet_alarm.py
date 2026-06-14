#!/usr/bin/python3
import argparse
import importlib.util
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "modbus-simulator" / "modbus_client.py"
SENDER_PATH = ROOT / "raw-ethernet" / "send_raw_packet.py"


def load_module(name, path):
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def wait_for_register(client, expected, timeout, interval):
	deadline = time.monotonic() + timeout
	last_values = None
	while time.monotonic() < deadline:
		last_values = client.read_holding(0, 3)
		if last_values[1] == expected:
			return last_values
		time.sleep(interval)
	raise TimeoutError(
		f"register 1 did not become {expected}; last registers: {last_values}"
	)


def run_case(sender, client, args, label, sequence, sensor, forced_output,
	     expected_output):
	sent = sender.send_frame(
		args.interface,
		sequence,
		sensor,
		args.threshold,
		forced_output,
	)
	final = wait_for_register(client, expected_output, args.timeout, args.interval)
	print(
		f"{label}: sent={sent} sequence={sequence} sensor={sensor} "
		f"threshold={args.threshold} forced_output={forced_output} final={final}"
	)


def parse_args():
	parser = argparse.ArgumentParser(
		description="Send raw Ethernet sensor packets and verify PLC output via Modbus."
	)
	parser.add_argument("--interface", "-i", default="enp2s0")
	parser.add_argument("--modbus-host", default="127.0.0.1")
	parser.add_argument("--modbus-port", type=int, default=1502)
	parser.add_argument("--threshold", type=int, default=500)
	parser.add_argument("--timeout", type=float, default=5.0)
	parser.add_argument("--interval", type=float, default=0.1)
	return parser.parse_args()


def main():
	args = parse_args()
	modbus_client = load_module("modbus_client", CLIENT_PATH)
	sender = load_module("send_raw_packet", SENDER_PATH)
	client = modbus_client.ModbusClient(args.modbus_host, args.modbus_port)

	try:
		run_case(sender, client, args, "LOW", 1, 400, 1, 0)
		run_case(sender, client, args, "HIGH", 2, 600, 0, 1)
		run_case(sender, client, args, "LOW-AGAIN", 3, 250, 1, 0)
	except PermissionError as exc:
		print(f"raw socket permission denied: {exc}", file=sys.stderr)
		print("run this demo as root or grant CAP_NET_RAW", file=sys.stderr)
		return 1
	except Exception as exc:
		print(f"raw Ethernet demo failed: {exc}", file=sys.stderr)
		return 1

	print("raw Ethernet demo passed")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
