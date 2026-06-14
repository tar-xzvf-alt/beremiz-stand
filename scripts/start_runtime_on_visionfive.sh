#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
RUNTIME_DIR=${2:-/root/beremiz-runtime/study-plc}
BIND_IP=${3:-10.42.0.211}
PORT=${4:-3000}
REMOTE_DIR=${5:-/root/beremiz-stand}
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
	EXT_ARGS=; \
	if [ -f '$COMPAT_EXTENSION' ]; then \
		EXT_ARGS=\"-e $COMPAT_EXTENSION\"; \
	fi; \
	nohup /usr/bin/python3 /usr/share/beremiz/Beremiz_service.py -i '$BIND_IP' -p '$PORT' -x 0 -t 0 -w off \$EXT_ARGS . >'$LOGFILE' 2>&1 & \
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
	echo 'Beremiz runtime started on $BIND_IP:$PORT'"
