#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
SUPERVISOR_BIN=${3:-/root/rt-supervisor/Build/src/alt-rt-supervisor}
CONTROLLER_BIN=${4:-/root/rt-supervisor/Build/src/controller-emu}
RUNTIME_WRAPPER=${5:-/root/beremiz-runtime/supervised-raw-plc/start_runtime.sh}
INTERFACE=${6:-end0}
TIMEOUT_US=${TIMEOUT_US:-${7:-5000000}}
RT_TRACE_SESSION_ID=${RT_TRACE_SESSION_ID:-}
RT_TRACE_MEASUREMENTS_PER_GROUP=${RT_TRACE_MEASUREMENTS_PER_GROUP:-}
RT_TRACE_SUPERVISOR_PATH=${RT_TRACE_SUPERVISOR_PATH:-/tmp/rt-supervisor-trace.jsonl}
RT_TRACE_CONTROLLER_PATH=${RT_TRACE_CONTROLLER_PATH:-/tmp/controller-emu-trace.jsonl}
RT_TRACE_EXPORTERS=${RT_TRACE_EXPORTERS:-1}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

"$SCRIPT_DIR/stop_supervised_stack.sh" "$VISIONFIVE" "$ROCKPI"

ssh "$VISIONFIVE" sh -s -- "$SUPERVISOR_BIN" "$RUNTIME_WRAPPER" \
	"$INTERFACE" "$TIMEOUT_US" "$RT_TRACE_SESSION_ID" \
	"$RT_TRACE_SUPERVISOR_PATH" "$RT_TRACE_EXPORTERS" <<'VISIONFIVE_REMOTE'
set -eu
SUPERVISOR_BIN=$1
RUNTIME_WRAPPER=$2
INTERFACE=$3
TIMEOUT_US=$4
TRACE_SESSION_ID=$5
TRACE_PATH=$6
TRACE_EXPORTERS=${7:-0}

if [ "$TRACE_SESSION_ID" = - ]; then
	TRACE_SESSION_ID=
fi

: > /root/alt-rt-supervisor.log
if [ -n "$TRACE_SESSION_ID" ]; then
	: > "$TRACE_PATH"
	if [ "$TRACE_EXPORTERS" = 1 ] && [ -x /root/rt-supervisor/scripts/trace_exporter.py ]; then
		nohup /root/rt-supervisor/scripts/trace_exporter.py \
			--listen 0.0.0.0 --port 9201 "$TRACE_PATH" \
			>/root/rt-trace-exporter.log 2>&1 &
		echo "visionfive trace_exporter pid=$!"
	fi
	RT_TRACE_PATH="$TRACE_PATH" nohup /root/rt-supervisor/scripts/run_supervisor.sh \
		"$INTERFACE" "$TIMEOUT_US" "$RUNTIME_WRAPPER" "$SUPERVISOR_BIN" \
		>/root/alt-rt-supervisor.log 2>&1 &
else
	nohup /root/rt-supervisor/scripts/run_supervisor.sh \
		"$INTERFACE" "$TIMEOUT_US" "$RUNTIME_WRAPPER" "$SUPERVISOR_BIN" \
		>/root/alt-rt-supervisor.log 2>&1 &
fi
echo "alt-rt-supervisor pid=$!"
VISIONFIVE_REMOTE

ssh "$VISIONFIVE" "ssh '$ROCKPI' sh -s -- '$CONTROLLER_BIN' '$INTERFACE' '$RT_TRACE_SESSION_ID' '$RT_TRACE_MEASUREMENTS_PER_GROUP' '$RT_TRACE_CONTROLLER_PATH' '$RT_TRACE_EXPORTERS'" <<'ROCKPI_REMOTE'
set -eu
CONTROLLER_BIN=$1
INTERFACE=$2
TRACE_SESSION_ID=$3
TRACE_MPG=$4
TRACE_PATH=$5
TRACE_EXPORTERS=${6:-0}

if [ "$TRACE_SESSION_ID" = - ]; then
	TRACE_SESSION_ID=
fi

: > /root/controller-emu.log
if [ -n "$TRACE_SESSION_ID" ] && [ -n "$TRACE_MPG" ]; then
	: > "$TRACE_PATH"
	if [ "$TRACE_EXPORTERS" = 1 ] && [ -x /root/rt-supervisor/scripts/trace_exporter.py ]; then
		nohup /root/rt-supervisor/scripts/trace_exporter.py \
			--listen 0.0.0.0 --port 9201 "$TRACE_PATH" \
			>/root/rt-trace-exporter.log 2>&1 &
		echo "rockpi trace_exporter pid=$!"
	fi
	RT_TRACE_PATH="$TRACE_PATH" \
	RT_TRACE_SESSION_ID="$TRACE_SESSION_ID" \
	RT_TRACE_MEASUREMENTS_PER_GROUP="$TRACE_MPG" \
		nohup /root/rt-supervisor/scripts/run_controller.sh \
		"$INTERFACE" "$CONTROLLER_BIN" >/root/controller-emu.log 2>&1 &
else
	nohup /root/rt-supervisor/scripts/run_controller.sh \
		"$INTERFACE" "$CONTROLLER_BIN" >/root/controller-emu.log 2>&1 &
fi
echo "controller-emu pid=$!"
ROCKPI_REMOTE

sleep 4
ssh "$VISIONFIVE" /root/pin_visionfive_supervised.sh
ssh "$VISIONFIVE" "ssh '$ROCKPI' /root/pin_rockpi_controller.sh"
