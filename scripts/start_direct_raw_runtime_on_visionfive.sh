#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
RAW_INTERFACE=${2:-end0}
RUNTIME_DIR=${3:-/root/beremiz-runtime/direct-raw-plc}
BIND_IP=${4:-10.42.0.211}
PORT=${5:-3000}
REMOTE_DIR=${6:-/root/beremiz-stand}
PIDFILE="$RUNTIME_DIR/beremiz_service.pid"
LOGFILE="$RUNTIME_DIR/beremiz_service.log"
COMPAT_EXTENSION="$REMOTE_DIR/scripts/beremiz_runtime_compat_15.py"

ssh "$TARGET" \
	"set -eu; \
	mkdir -p '$RUNTIME_DIR'; \
	if [ -f '$PIDFILE' ] && kill -0 \"\$(cat '$PIDFILE')\" 2>/dev/null; then \
		echo 'Beremiz runtime already running on $BIND_IP:$PORT'; \
		exit 0; \
	fi; \
	rm -f '$PIDFILE'; \
	cd '$RUNTIME_DIR'; \
	RAW_ETH_INTERFACE='$RAW_INTERFACE' nohup /usr/bin/python3 /usr/share/beremiz/Beremiz_service.py \
		-i '$BIND_IP' -p '$PORT' -x 0 -t 0 -w off -e '$COMPAT_EXTENSION' . >'$LOGFILE' 2>&1 & \
	echo \$! > '$PIDFILE'; \
	sleep 2; \
	if ! kill -0 \"\$(cat '$PIDFILE')\" 2>/dev/null; then \
		echo 'Beremiz runtime failed to start; log follows:' >&2; \
		tail -n 80 '$LOGFILE' >&2; \
		exit 1; \
	fi; \
	grep -q 'Current working directory' '$LOGFILE' || { \
		echo 'Beremiz runtime did not report readiness; log follows:' >&2; \
		tail -n 80 '$LOGFILE' >&2; \
		exit 1; \
	}; \
	echo 'Beremiz direct raw runtime started on $BIND_IP:$PORT, raw interface $RAW_INTERFACE'"
