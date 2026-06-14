from runtime.PLCObject import PLCObject
from erpc_interface.erpc_PLCObject import common
from inspect import getmembers, isfunction

import erpc
from erpc_interface.erpc_PLCObject.interface import IBeremizPLCObjectService
from erpc_interface.erpc_PLCObject.server import BeremizPLCObjectServiceService
from runtime import GetPLCObjectSingleton as PLC
from runtime.loglevels import LogLevelsDict
import runtime.eRPCServer as erpc_server_module


# Beremiz 1.5 clients expect log_message.sec as uint64, while the 1.4
# runtime on VisionFive 2 generates uint32 eRPC stubs.

def write_log_message_15(self, codec):
	if self.msg is None:
		raise ValueError("msg is None")
	codec.write_string(self.msg)
	if self.tick is None:
		raise ValueError("tick is None")
	codec.write_uint32(self.tick)
	if self.sec is None:
		raise ValueError("sec is None")
	codec.write_uint64(self.sec)
	if self.nsec is None:
		raise ValueError("nsec is None")
	codec.write_uint32(self.nsec)


common.log_message._write = write_log_message_15

original_get_log_message = PLCObject.GetLogMessage


def get_log_message_15(self, level, msgid):
	message = original_get_log_message(self, level, msgid)
	if message is None:
		return "", 0, 0, 0
	return message


PLCObject.GetLogMessage = get_log_message_15


# Beremiz 1.4 only catches erpc.transport.ConnectionClosed here. Killing a
# CLI/IDE client with timeout can raise ConnectionResetError and stop the RPC
# thread while leaving the service process alive but unresponsive.
def loop_with_connection_reset(self, when_ready):
	if self._to_be_published():
		self.Publish()

	handler = type(
		"PLCObjectServiceHandlder",
		(IBeremizPLCObjectService,),
		{
			name: erpc_server_module.rpc_wrapper(name, self)
			for name, _func in getmembers(IBeremizPLCObjectService, isfunction)
		},
	)()
	service = BeremizPLCObjectServiceService(handler)

	self.transport = erpc.transport.TCPTransport(self.ip_addr, self.port, True)
	self.server = erpc.simple_server.SimpleServer(
		self.transport, erpc.basic_codec.BasicCodec
	)
	self.server.add_service(service)

	when_ready()

	while self.continueloop:
		try:
			self.server.run()
		except (erpc.transport.ConnectionClosed, ConnectionResetError):
			PLC().LogMessage(LogLevelsDict["DEBUG"], "eRPC client disconnected")
		except Exception as exc:
			self.Unpublish()
			raise exc


erpc_server_module.eRPCServer.Loop = loop_with_connection_reset
