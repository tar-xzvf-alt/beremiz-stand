#!/usr/bin/env python3
"""Tiny Modbus TCP client used to verify the simulator."""

import argparse
import socket
import struct


DEFAULT_PORT = 1502


class ModbusClient:
	def __init__(self, host, port, unit_id=1, timeout=3.0):
		self.host = host
		self.port = port
		self.unit_id = unit_id
		self.timeout = timeout
		self.transaction_id = 1

	def read_holding(self, start, count):
		return self._read_registers(3, start, count)

	def read_input(self, start, count):
		return self._read_registers(4, start, count)

	def write_single(self, address, value):
		pdu = struct.pack(">BHH", 6, address, value & 0xffff)
		response = self._request(pdu)
		function, echoed_address, echoed_value = struct.unpack(">BHH", response)
		if function != 6 or echoed_address != address or echoed_value != (value & 0xffff):
			raise RuntimeError("unexpected write-single response")

	def write_multiple(self, start, values):
		payload = b"".join(struct.pack(">H", value & 0xffff) for value in values)
		pdu = struct.pack(">BHHB", 16, start, len(values), len(payload)) + payload
		response = self._request(pdu)
		function, echoed_start, echoed_count = struct.unpack(">BHH", response)
		if function != 16 or echoed_start != start or echoed_count != len(values):
			raise RuntimeError("unexpected write-multiple response")

	def _read_registers(self, function, start, count):
		pdu = struct.pack(">BHH", function, start, count)
		response = self._request(pdu)
		if response[0] != function:
			raise RuntimeError(f"unexpected function code {response[0]}")
		byte_count = response[1]
		return list(struct.unpack(f">{byte_count // 2}H", response[2:2 + byte_count]))

	def _request(self, pdu):
		transaction_id = self.transaction_id
		self.transaction_id += 1
		header = struct.pack(">HHHB", transaction_id, 0, len(pdu) + 1,
				     self.unit_id)
		with socket.create_connection((self.host, self.port), self.timeout) as sock:
			sock.sendall(header + pdu)
			response_header = recv_exact(sock, 7)
			resp_tid, protocol_id, length, _unit_id = struct.unpack(
				">HHHB", response_header)
			if resp_tid != transaction_id or protocol_id != 0:
				raise RuntimeError("invalid Modbus TCP header")
			response = recv_exact(sock, length - 1)
			if response[0] & 0x80:
				raise RuntimeError(
					f"Modbus exception function={response[0] & 0x7f} code={response[1]}")
			return response


def recv_exact(sock, size):
	data = bytearray()
	while len(data) < size:
		chunk = sock.recv(size - len(data))
		if not chunk:
			raise RuntimeError("connection closed while reading response")
		data.extend(chunk)
	return bytes(data)


def parse_args():
	parser = argparse.ArgumentParser(description="Modbus TCP test client")
	parser.add_argument("host")
	parser.add_argument("--port", type=int, default=DEFAULT_PORT)
	subparsers = parser.add_subparsers(dest="command", required=True)

	read_holding = subparsers.add_parser("read-holding")
	read_holding.add_argument("start", type=int)
	read_holding.add_argument("count", type=int)

	read_input = subparsers.add_parser("read-input")
	read_input.add_argument("start", type=int)
	read_input.add_argument("count", type=int)

	write_single = subparsers.add_parser("write-single")
	write_single.add_argument("address", type=int)
	write_single.add_argument("value", type=int)

	write_multiple = subparsers.add_parser("write-multiple")
	write_multiple.add_argument("start", type=int)
	write_multiple.add_argument("values", type=int, nargs="+")

	return parser.parse_args()


def main():
	args = parse_args()
	client = ModbusClient(args.host, args.port)

	if args.command == "read-holding":
		print(client.read_holding(args.start, args.count))
	elif args.command == "read-input":
		print(client.read_input(args.start, args.count))
	elif args.command == "write-single":
		client.write_single(args.address, args.value)
		print("ok")
	elif args.command == "write-multiple":
		client.write_multiple(args.start, args.values)
		print("ok")


if __name__ == "__main__":
	main()
