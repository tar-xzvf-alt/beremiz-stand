#!/usr/bin/env python3
"""Configure the study PLC project for the Modbus simulator."""

import argparse
from pathlib import Path


PLC_XML = """<?xml version='1.0' encoding='utf-8'?>
<project xmlns="http://www.plcopen.org/xml/tc6_0201" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:ns1="http://www.plcopen.org/xml/tc6.xsd">
  <fileHeader companyName="Study Stand" productName="Beremiz Study PLC" productVersion="1" creationDateTime="2026-06-11T14:12:07"/>
  <contentHeader name="Beremiz Modbus Study PLC" modificationDateTime="2026-06-11T15:00:00">
    <coordinateInfo>
      <fbd>
        <scaling x="8" y="8"/>
      </fbd>
      <ld>
        <scaling x="8" y="8"/>
      </ld>
      <sfc>
        <scaling x="8" y="8"/>
      </sfc>
    </coordinateInfo>
  </contentHeader>
  <types>
    <dataTypes/>
    <pous>
      <pou name="plc_prg" pouType="program">
        <interface>
          <localVars>
            <variable name="ReadRequestExecute" address="%QX0.0.0.0.0">
              <type><BOOL/></type>
            </variable>
            <variable name="WriteRequestExecute" address="%QX0.0.1.0.0">
              <type><BOOL/></type>
            </variable>
          </localVars>
          <localVars>
            <variable name="SensorRegister" address="%IW0.0.0.0">
              <type><WORD/></type>
            </variable>
            <variable name="RemoteOutputRegister" address="%IW0.0.0.1">
              <type><WORD/></type>
            </variable>
            <variable name="ThresholdRegister" address="%IW0.0.0.2">
              <type><WORD/></type>
            </variable>
            <variable name="OutputCommandRegister" address="%QW0.0.1.1">
              <type><WORD/></type>
            </variable>
          </localVars>
          <localVars>
            <variable name="sensor_value">
              <type><UINT/></type>
            </variable>
            <variable name="threshold">
              <type><UINT/></type>
            </variable>
            <variable name="remote_output_echo">
              <type><UINT/></type>
            </variable>
            <variable name="alarm">
              <type><BOOL/></type>
            </variable>
            <variable name="output_command">
              <type><UINT/></type>
            </variable>
          </localVars>
        </interface>
        <body>
          <ST>
            <xhtml:p><![CDATA[ReadRequestExecute := TRUE;
WriteRequestExecute := TRUE;

sensor_value := WORD_TO_UINT(SensorRegister);
threshold := WORD_TO_UINT(ThresholdRegister);
remote_output_echo := WORD_TO_UINT(RemoteOutputRegister);

alarm := sensor_value > threshold;

IF alarm THEN
    output_command := UINT#1;
ELSE
    output_command := UINT#0;
END_IF;

OutputCommandRegister := UINT_TO_WORD(output_command);]]></xhtml:p>
          </ST>
        </body>
      </pou>
    </pous>
  </types>
  <instances>
    <configurations>
      <configuration name="config">
        <resource name="resource1">
          <task name="task0" interval="T#100ms" priority="0">
            <pouInstance name="instance0" typeName="plc_prg"/>
          </task>
        </resource>
      </configuration>
    </configurations>
  </instances>
</project>
"""


BEREMIZ_XML = """<?xml version='1.0' encoding='utf-8'?>
<BeremizRoot xmlns:xsd="http://www.w3.org/2001/XMLSchema" URI_location="LOCAL://">
  <TargetType>
    <Linux/>
  </TargetType>
</BeremizRoot>
"""


FILES = {
	"beremiz.xml": BEREMIZ_XML,
	"plc.xml": PLC_XML,
	"modbus_0@modbus/baseconfnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<BaseParams xmlns:xsd="http://www.w3.org/2001/XMLSchema" IEC_Channel="0" Name="modbus_0"/>
""",
	"modbus_0@modbus/confnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<ModbusRoot xmlns:xsd="http://www.w3.org/2001/XMLSchema"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/baseconfnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<BaseParams xmlns:xsd="http://www.w3.org/2001/XMLSchema" IEC_Channel="0" Name="ModbusTCPclient_0"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/confnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<ModbusTCPclient xmlns:xsd="http://www.w3.org/2001/XMLSchema" Configuration_Name="Simulator client" Remote_IP_Address="10.42.0.1" Remote_Port_Number="1502" Invocation_Rate_in_ms="100" Request_Delay_in_ms="0"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/ReadHolding_0@ModbusRequest/baseconfnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<BaseParams xmlns:xsd="http://www.w3.org/2001/XMLSchema" IEC_Channel="0" Name="ReadHolding_0"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/ReadHolding_0@ModbusRequest/confnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<ModbusRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema" Function="03 - Read Holding Registers" SlaveID="1" Nr_of_Channels="3" Start_Address="0" Timeout_in_ms="1000"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/WriteOutput_1@ModbusRequest/baseconfnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<BaseParams xmlns:xsd="http://www.w3.org/2001/XMLSchema" IEC_Channel="1" Name="WriteOutput_1"/>
""",
	"modbus_0@modbus/ModbusTCPclient_0@ModbusTCPclient/WriteOutput_1@ModbusRequest/confnode.xml": """<?xml version='1.0' encoding='utf-8'?>
<ModbusRequest xmlns:xsd="http://www.w3.org/2001/XMLSchema" Function="06 - Write Single Register" SlaveID="1" Nr_of_Channels="1" Start_Address="1" Timeout_in_ms="1000" Write_on_change="true"/>
""",
}


def parse_args():
	parser = argparse.ArgumentParser(description="Configure study-plc for Modbus TCP")
	parser.add_argument(
		"project_dir", nargs="?", default="beremiz-project/study-plc",
		help="Beremiz project directory")
	return parser.parse_args()


def main():
	args = parse_args()
	project_dir = Path(args.project_dir).resolve()
	if not project_dir.is_dir():
		print(f"Project directory not found: {project_dir}")
		return 1

	for relative_path, content in FILES.items():
		path = project_dir / relative_path
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content, encoding="utf-8")
		print(f"wrote {path.relative_to(project_dir)}")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
