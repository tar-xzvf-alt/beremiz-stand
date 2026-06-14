#!/usr/bin/python3
import argparse
import importlib.util
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "modbus-simulator" / "modbus_client.py"


def load_modbus_client():
	spec = importlib.util.spec_from_file_location("modbus_client", CLIENT_PATH)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module.ModbusClient


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


def run_case(client, label, sensor, threshold, forced_output, expected_output,
	     timeout, interval):
	client.write_single(2, threshold)
	client.write_single(1, forced_output)
	client.write_single(0, sensor)
	initial = client.read_holding(0, 3)
	final = wait_for_register(client, expected_output, timeout, interval)
	print(
		f"{label}: sensor={sensor}, threshold={threshold}, "
		f"forced_output={forced_output}, initial={initial}, final={final}"
	)


def parse_args():
	parser = argparse.ArgumentParser(
		description="Demonstrate study-plc alarm/output switching via Modbus registers."
	)
	parser.add_argument("--host", default="127.0.0.1")
	parser.add_argument("--port", type=int, default=1502)
	parser.add_argument("--threshold", type=int, default=500)
	parser.add_argument("--timeout", type=float, default=5.0)
	parser.add_argument("--interval", type=float, default=0.1)
	return parser.parse_args()


def main():
	args = parse_args()
	ModbusClient = load_modbus_client()
	client = ModbusClient(args.host, args.port)

	try:
		run_case(client, "LOW", 400, args.threshold, 1, 0,
			 args.timeout, args.interval)
		run_case(client, "HIGH", 600, args.threshold, 0, 1,
			 args.timeout, args.interval)
		run_case(client, "LOW-AGAIN", 250, args.threshold, 1, 0,
			 args.timeout, args.interval)
	except Exception as exc:
		print(f"demo failed: {exc}", file=sys.stderr)
		return 1

	print("demo passed")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
