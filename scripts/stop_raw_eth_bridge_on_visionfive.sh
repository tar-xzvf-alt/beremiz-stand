#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
BRIDGE_DIR=${2:-/root/beremiz-runtime/raw-eth-bridge}
PIDFILE="$BRIDGE_DIR/raw_eth_bridge.pid"

ssh "$TARGET" \
	"set -eu; \
	if [ ! -f '$PIDFILE' ]; then \
		echo 'raw Ethernet bridge is not running'; \
		exit 0; \
	fi; \
	PID=\"\$(cat '$PIDFILE')\"; \
	if ! kill -0 \"\$PID\" 2>/dev/null; then \
		rm -f '$PIDFILE'; \
		echo 'raw Ethernet bridge is not running'; \
		exit 0; \
	fi; \
	kill \"\$PID\"; \
	for _ in 1 2 3 4 5; do \
		if ! kill -0 \"\$PID\" 2>/dev/null; then \
			rm -f '$PIDFILE'; \
			echo 'raw Ethernet bridge stopped'; \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	kill -KILL \"\$PID\" 2>/dev/null || true; \
	rm -f '$PIDFILE'; \
	echo 'raw Ethernet bridge killed'"
