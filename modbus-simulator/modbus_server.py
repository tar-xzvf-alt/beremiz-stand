#!/usr/bin/env python3
"""Small Modbus TCP simulator for the Beremiz study stand.

Implements enough of Modbus TCP for the first PLC integration tests:
- function 3: read holding registers
- function 4: read input registers
- function 6: write single holding register
- function 16: write multiple holding registers
"""

import argparse
import socketserver
import struct
import threading
import time
from datetime import datetime


REGISTER_COUNT = 128
DEFAULT_PORT = 1502


class RegisterBank:
	def __init__(self):
		self._lock = threading.Lock()
		self.holding = [0] * REGISTER_COUNT
		self.input = [0] * REGISTER_COUNT
		self.holding[0] = 123  # sensor_value
		self.holding[1] = 0    # output_command written by PLC
		self.holding[2] = 500  # threshold used by PLC logic

	def read_holding(self, start, count):
		with self._lock:
			return self._read(self.holding, start, count)

	def read_input(self, start, count):
		with self._lock:
			self.input[0] = self.holding[0]
			self.input[1] = self.holding[1]
			self.input[2] = self.holding[2]
			return self._read(self.input, start, count)

	def write_holding(self, start, values):
		with self._lock:
			if start < 0 or start + len(values) > len(self.holding):
				raise ValueError("register address out of range")
			for offset, value in enumerate(values):
				self.holding[start + offset] = value & 0xffff

	def snapshot(self):
		with self._lock:
			return self.holding[0], self.holding[1], self.holding[2]

	@staticmethod
	def _read(registers, start, count):
		if count < 1 or count > 125:
			raise ValueError("invalid register count")
		if start < 0 or start + count > len(registers):
			raise ValueError("register address out of range")
		return registers[start:start + count]


class ModbusTCPServer(socketserver.ThreadingTCPServer):
	allow_reuse_address = True

	def __init__(self, server_address, handler_class, registers, verbose=False):
		super().__init__(server_address, handler_class)
		self.registers = registers
		self.verbose = verbose


class ModbusTCPHandler(socketserver.BaseRequestHandler):
	def handle(self):
		peer = f"{self.client_address[0]}:{self.client_address[1]}"
		log(self.server, f"client connected: {peer}")
		while True:
			header = self._recv_exact(7)
			if not header:
				break

			transaction_id, protocol_id, length, unit_id = struct.unpack(
				">HHHB", header)
			if protocol_id != 0 or length < 2:
				break

			pdu = self._recv_exact(length - 1)
			if not pdu:
				break

			response = self._handle_pdu(pdu)
			response_header = struct.pack(
				">HHHB", transaction_id, 0, len(response) + 1, unit_id)
			self.request.sendall(response_header + response)

		log(self.server, f"client disconnected: {peer}")

	def _handle_pdu(self, pdu):
		function = pdu[0]
		try:
			if function == 3:
				return self._read_registers(function, pdu,
								   self.server.registers.read_holding)
			if function == 4:
				return self._read_registers(function, pdu,
								   self.server.registers.read_input)
			if function == 6:
				return self._write_single(pdu)
			if function == 16:
				return self._write_multiple(pdu)
			return exception_response(function, 1)
		except (struct.error, ValueError) as exc:
			log(self.server, f"bad request: {exc}")
			return exception_response(function, 3)

	def _read_registers(self, function, pdu, reader):
		start, count = struct.unpack(">HH", pdu[1:5])
		values = reader(start, count)
		payload = b"".join(struct.pack(">H", value) for value in values)
		log(self.server, f"read fc={function} start={start} count={count} values={values}")
		return struct.pack("BB", function, len(payload)) + payload

	def _write_single(self, pdu):
		address, value = struct.unpack(">HH", pdu[1:5])
		self.server.registers.write_holding(address, [value])
		log(self.server, f"write fc=6 address={address} value={value}")
		return pdu[:5]

	def _write_multiple(self, pdu):
		start, count, byte_count = struct.unpack(">HHB", pdu[1:6])
		if byte_count != count * 2:
			raise ValueError("byte count does not match register count")
		values = list(struct.unpack(f">{count}H", pdu[6:6 + byte_count]))
		self.server.registers.write_holding(start, values)
		log(self.server, f"write fc=16 start={start} values={values}")
		return struct.pack(">BHH", 16, start, count)

	def _recv_exact(self, size):
		data = bytearray()
		while len(data) < size:
			chunk = self.request.recv(size - len(data))
			if not chunk:
				return None
			data.extend(chunk)
		return bytes(data)


def exception_response(function, code):
	return struct.pack("BB", function | 0x80, code)


def log(server, message):
	if server.verbose:
		print(f"{datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def sensor_loop(registers, interval, step):
	while True:
		sensor, output, threshold = registers.snapshot()
		next_sensor = (sensor + step) % 1000
		registers.write_holding(0, [next_sensor])
		print(
			f"{datetime.now().isoformat(timespec='seconds')} "
			f"sensor={next_sensor} output_command={output} threshold={threshold}",
			flush=True,
		)
		time.sleep(interval)


def parse_args():
	parser = argparse.ArgumentParser(description="Modbus TCP simulator")
	parser.add_argument("--host", default="0.0.0.0", help="address to bind")
	parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port")
	parser.add_argument("--verbose", action="store_true", help="log each request")
	parser.add_argument(
		"--auto-sensor", action="store_true",
		help="periodically change holding register 0",
	)
	parser.add_argument("--sensor-interval", type=float, default=1.0)
	parser.add_argument("--sensor-step", type=int, default=37)
	return parser.parse_args()


def main():
	args = parse_args()
	registers = RegisterBank()

	if args.auto_sensor:
		thread = threading.Thread(
			target=sensor_loop,
			args=(registers, args.sensor_interval, args.sensor_step),
			daemon=True,
		)
		thread.start()

	with ModbusTCPServer((args.host, args.port), ModbusTCPHandler,
					 registers, args.verbose) as server:
		print(f"Modbus TCP simulator listening on {args.host}:{args.port}")
		print("Holding registers: 0=sensor_value, 1=output_command, 2=threshold")
		server.serve_forever()


if __name__ == "__main__":
	main()
