#!/usr/bin/python3
import argparse
import importlib.util
import socket
import struct
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT_PATH = ROOT / "modbus-simulator" / "modbus_client.py"
ETH_P_EXPERIMENT = 0x1122
PAYLOAD = struct.Struct("!4sBIHHH")


def load_modbus_client():
	spec = importlib.util.spec_from_file_location("modbus_client", CLIENT_PATH)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module.ModbusClient


def parse_payload(data):
	if len(data) < PAYLOAD.size:
		raise ValueError(f"payload too short: {len(data)} bytes")
	magic, version, sequence, sensor, threshold, forced_output = PAYLOAD.unpack(
		data[:PAYLOAD.size]
	)
	if magic != b"BETH":
		raise ValueError(f"bad magic: {magic!r}")
	if version != 1:
		raise ValueError(f"unsupported version: {version}")
	if forced_output not in (0, 1):
		raise ValueError(f"forced_output must be 0 or 1, got {forced_output}")
	return sequence, sensor, threshold, forced_output


def format_mac(raw):
	return ":".join(f"{byte:02x}" for byte in raw)


def run_bridge(args):
	ModbusClient = load_modbus_client()
	client = ModbusClient(args.modbus_host, args.modbus_port)

	with socket.socket(
		socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_EXPERIMENT)
	) as sock:
		sock.bind((args.interface, 0))
		print(
			f"raw Ethernet bridge listening on {args.interface}, "
			f"EtherType=0x{ETH_P_EXPERIMENT:04x}, "
			f"Modbus={args.modbus_host}:{args.modbus_port}"
		)
		sys.stdout.flush()

		processed = 0
		while args.count == 0 or processed < args.count:
			frame = sock.recv(2048)
			if len(frame) < 14:
				continue
			dst = frame[0:6]
			src = frame[6:12]
			ether_type = struct.unpack("!H", frame[12:14])[0]
			if ether_type != ETH_P_EXPERIMENT:
				continue

			try:
				sequence, sensor, threshold, forced_output = parse_payload(
					frame[14:]
				)
			except ValueError as exc:
				print(f"ignored frame from {format_mac(src)}: {exc}")
				sys.stdout.flush()
				continue

			client.write_single(2, threshold)
			client.write_single(1, forced_output)
			client.write_single(0, sensor)
			registers = client.read_holding(0, 3)
			print(
				f"seq={sequence} src={format_mac(src)} dst={format_mac(dst)} "
				f"sensor={sensor} threshold={threshold} "
				f"forced_output={forced_output} registers={registers}"
			)
			sys.stdout.flush()

			processed += 1


def parse_args():
	parser = argparse.ArgumentParser(
		description="Receive raw Ethernet packets and write their values to Modbus registers."
	)
	parser.add_argument("--interface", "-i", default="end1")
	parser.add_argument("--modbus-host", default="10.42.0.1")
	parser.add_argument("--modbus-port", type=int, default=1502)
	parser.add_argument(
		"--count",
		type=int,
		default=0,
		help="number of valid packets to process; 0 means forever",
	)
	return parser.parse_args()


def main():
	try:
		run_bridge(parse_args())
	except KeyboardInterrupt:
		return 0
	except Exception as exc:
		print(f"bridge failed: {exc}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
