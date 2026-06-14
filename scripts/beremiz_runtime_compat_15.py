from runtime.PLCObject import PLCObject
from erpc_interface.erpc_PLCObject import common


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
