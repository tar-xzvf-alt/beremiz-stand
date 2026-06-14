#!/usr/bin/python3
import argparse
import socket
import struct


ETH_P_EXPERIMENT = 0x1122
DEST_BROADCAST = b"\xff\xff\xff\xff\xff\xff"
PAYLOAD = struct.Struct("!4sBIHHH")


def get_interface_mac(interface):
	probe = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
	try:
		probe.bind((interface, 0))
		return probe.getsockname()[4]
	finally:
		probe.close()


def build_payload(sequence, sensor, threshold, forced_output):
	return PAYLOAD.pack(
		b"BETH",
		1,
		sequence & 0xFFFFFFFF,
		sensor & 0xFFFF,
		threshold & 0xFFFF,
		forced_output & 0xFFFF,
	)


def send_frame(interface, sequence, sensor, threshold, forced_output):
	source_mac = get_interface_mac(interface)
	ether_type = struct.pack("!H", ETH_P_EXPERIMENT)
	payload = build_payload(sequence, sensor, threshold, forced_output)
	frame = DEST_BROADCAST + source_mac + ether_type + payload

	with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as sock:
		sock.bind((interface, 0))
		return sock.send(frame)


def parse_args():
	parser = argparse.ArgumentParser(
		description="Send a raw Ethernet sensor packet for the Beremiz PLC experiment."
	)
	parser.add_argument("--interface", "-i", default="enp2s0")
	parser.add_argument("--sequence", type=int, default=1)
	parser.add_argument("--sensor", type=int, required=True)
	parser.add_argument("--threshold", type=int, default=500)
	parser.add_argument("--forced-output", type=int, choices=(0, 1), required=True)
	return parser.parse_args()


def main():
	args = parse_args()
	sent = send_frame(
		args.interface,
		args.sequence,
		args.sensor,
		args.threshold,
		args.forced_output,
	)
	print(
		f"sent {sent} bytes on {args.interface}: "
		f"sequence={args.sequence} sensor={args.sensor} "
		f"threshold={args.threshold} forced_output={args.forced_output}"
	)


if __name__ == "__main__":
	main()
