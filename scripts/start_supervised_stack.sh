#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
SUPERVISOR_BIN=${3:-/root/rt-supervisor/Build/src/alt-rt-supervisor}
CONTROLLER_BIN=${4:-/root/rt-supervisor/Build/src/controller-emu}
RUNTIME_WRAPPER=${5:-/root/beremiz-runtime/supervised-raw-plc/start_runtime.sh}
INTERFACE=${6:-end0}
TIMEOUT_US=${TIMEOUT_US:-${7:-5000000}}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

"$SCRIPT_DIR/stop_supervised_stack.sh" "$VISIONFIVE" "$ROCKPI"

ssh "$VISIONFIVE" sh -s -- "$SUPERVISOR_BIN" "$RUNTIME_WRAPPER" "$INTERFACE" "$TIMEOUT_US" <<'VISIONFIVE_REMOTE'
set -eu
SUPERVISOR_BIN=$1
RUNTIME_WRAPPER=$2
INTERFACE=$3
TIMEOUT_US=$4

: > /root/alt-rt-supervisor.log
nohup /root/rt-supervisor/scripts/run_supervisor.sh \
	"$INTERFACE" "$TIMEOUT_US" "$RUNTIME_WRAPPER" "$SUPERVISOR_BIN" \
	>/root/alt-rt-supervisor.log 2>&1 &
echo "alt-rt-supervisor pid=$!"
VISIONFIVE_REMOTE

ssh "$VISIONFIVE" "ssh '$ROCKPI' sh -s -- '$CONTROLLER_BIN' '$INTERFACE'" <<'ROCKPI_REMOTE'
set -eu
CONTROLLER_BIN=$1
INTERFACE=$2

: > /root/controller-emu.log
nohup /root/rt-supervisor/scripts/run_controller.sh \
	"$INTERFACE" "$CONTROLLER_BIN" >/root/controller-emu.log 2>&1 &
echo "controller-emu pid=$!"
ROCKPI_REMOTE

sleep 4
ssh "$VISIONFIVE" /root/pin_visionfive_supervised.sh
ssh "$VISIONFIVE" "ssh '$ROCKPI' /root/pin_rockpi_controller.sh"
