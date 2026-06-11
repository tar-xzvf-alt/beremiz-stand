#!/usr/bin/python3
import argparse
import sys

sys.path.insert(0, "/usr/share/beremiz")

import erpc
from erpc_interface.erpc_PLCObject.client import BeremizPLCObjectServiceClient
from erpc_interface.erpc_PLCObject.common import PLCstatus_enum


STATUS_NAMES = {
	value: name
	for name, value in vars(PLCstatus_enum).items()
	if not name.startswith("_") and isinstance(value, int)
}


def parse_erpc_uri(uri):
	if not uri.startswith("ERPC://"):
		raise ValueError("only ERPC://host[:port] is supported")
	location = uri.split("://", 1)[1]
	host, separator, port = location.partition(":")
	if not host:
		raise ValueError("missing host in URI")
	return host, int(port) if separator else 3000


def main():
	parser = argparse.ArgumentParser(
		description="Check Beremiz ERPC runtime status without reading runtime logs."
	)
	parser.add_argument("uri", nargs="?", default="ERPC://10.42.0.211:3000")
	args = parser.parse_args()

	host, port = parse_erpc_uri(args.uri)
	transport = erpc.transport.TCPTransport(host, port, False)
	manager = erpc.client.ClientManager(transport, erpc.basic_codec.BasicCodec)
	client = BeremizPLCObjectServiceClient(manager)

	status_ref = erpc.Reference()
	result = client.GetPLCstatus(status_ref)
	if result != 0:
		raise SystemExit(f"GetPLCstatus failed with code {result}")

	status = status_ref.value
	status_name = STATUS_NAMES.get(status.PLCstatus, f"unknown({status.PLCstatus})")
	print(f"PLC Status: {status_name}")
	print(f"Log counts: {status.logcounts}")


if __name__ == "__main__":
	main()
