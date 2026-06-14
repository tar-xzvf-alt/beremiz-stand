#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
INTERFACE=${3:-end1}
MODBUS_HOST=${4:-10.42.0.1}
MODBUS_PORT=${5:-1502}
BRIDGE_DIR=${6:-/root/beremiz-runtime/raw-eth-bridge}
PIDFILE="$BRIDGE_DIR/raw_eth_bridge.pid"
LOGFILE="$BRIDGE_DIR/raw_eth_bridge.log"

ssh "$TARGET" \
	"set -eu; \
	mkdir -p '$BRIDGE_DIR'; \
	if [ -f '$PIDFILE' ] && kill -0 \"\$(cat '$PIDFILE')\" 2>/dev/null; then \
		echo 'raw Ethernet bridge already running on $INTERFACE'; \
		exit 0; \
	fi; \
	rm -f '$PIDFILE'; \
	cd '$REMOTE_DIR'; \
	nohup /usr/bin/python3 scripts/raw_eth_to_modbus_bridge.py \
		--interface '$INTERFACE' \
		--modbus-host '$MODBUS_HOST' \
		--modbus-port '$MODBUS_PORT' \
		>'$LOGFILE' 2>&1 & \
	echo \$! > '$PIDFILE'; \
	sleep 1; \
	if ! kill -0 \"\$(cat '$PIDFILE')\" 2>/dev/null; then \
		echo 'raw Ethernet bridge failed to start; log follows:' >&2; \
		tail -n 80 '$LOGFILE' >&2; \
		exit 1; \
	fi; \
	echo 'raw Ethernet bridge started on $INTERFACE'"
