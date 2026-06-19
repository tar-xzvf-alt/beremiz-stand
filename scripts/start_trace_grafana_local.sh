#!/bin/sh
set -eu

RT_TESTER_DIR=${RT_TESTER_DIR:-/home/taranev/work_repos/rt/rt-tester}
GRAFANA_BIN=${GRAFANA_BIN:-/bin/grafana-server}
GRAFANA_HOME=${GRAFANA_HOME:-/usr/share/grafana}
TRACE_GRAFANA_ADDR=${TRACE_GRAFANA_ADDR:-127.0.0.1}
TRACE_GRAFANA_PORT=${TRACE_GRAFANA_PORT:-3001}
RUNTIME_DIR=${TRACE_GRAFANA_RUNTIME_DIR:-/tmp/rt-trace-grafana-local}
DATA_DIR=${TRACE_GRAFANA_DATA_DIR:-$RUNTIME_DIR/data}
LOG_DIR=${TRACE_GRAFANA_LOG_DIR:-$RUNTIME_DIR/logs}
PLUGIN_DIR=${TRACE_GRAFANA_PLUGIN_DIR:-$RUNTIME_DIR/plugins}
PROVISIONING_DIR=${TRACE_GRAFANA_PROVISIONING_DIR:-$RT_TESTER_DIR/grafana/provisioning}
PID_FILE=$RUNTIME_DIR/grafana.pid

is_alive()
{
	pid=$1
	[ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

grafana_pids()
{
	ps -eo pid,args | awk -v data="cfg:paths.data=$DATA_DIR" \
		'/[g]rafana/ && index($0, data) { print $1 }'
}

check_http()
{
	url=$1
	python3 - "$url" <<'PY'
import sys
import urllib.request

urllib.request.urlopen(sys.argv[1], timeout=10).read(1)
PY
}

http_ready()
{
	url=$1
	python3 - "$url" <<'PY'
import sys
import urllib.request

try:
    urllib.request.urlopen(sys.argv[1], timeout=2).read(1)
except Exception:
    raise SystemExit(1)
PY
}

if [ ! -x "$GRAFANA_BIN" ]; then
	echo "Grafana binary not found: $GRAFANA_BIN" >&2
	exit 1
fi

if [ ! -d "$GRAFANA_HOME" ]; then
	echo "Grafana home not found: $GRAFANA_HOME" >&2
	exit 1
fi

if [ ! -d "$PROVISIONING_DIR" ]; then
	echo "Grafana provisioning not found: $PROVISIONING_DIR" >&2
	exit 1
fi

mkdir -p "$RUNTIME_DIR" "$DATA_DIR" "$LOG_DIR" "$PLUGIN_DIR"

if [ -f "$PID_FILE" ]; then
	pid=$(cat "$PID_FILE")
	if is_alive "$pid" && http_ready "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/api/health"; then
		echo "trace Grafana already running pid=$pid"
		echo "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/d/rt-trace-stages"
		exit 0
	fi
	rm -f "$PID_FILE"
fi

pids=$(grafana_pids | tr '\n' ' ')
if [ -n "$pids" ]; then
	set -- $pids
	if http_ready "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/api/health"; then
		echo "$1" >"$PID_FILE"
		echo "trace Grafana already running pid=$1"
		echo "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/d/rt-trace-stages"
		exit 0
	fi
	echo "trace Grafana stale process found; stopping $pids"
	kill $pids 2>/dev/null || true
fi

nohup "$GRAFANA_BIN" \
	--homepath "$GRAFANA_HOME" \
	cfg:paths.data="$DATA_DIR" \
	cfg:paths.logs="$LOG_DIR" \
	cfg:paths.plugins="$PLUGIN_DIR" \
	cfg:paths.provisioning="$PROVISIONING_DIR" \
	cfg:server.http_addr="$TRACE_GRAFANA_ADDR" \
	cfg:server.http_port="$TRACE_GRAFANA_PORT" \
	cfg:security.admin_user=admin \
	cfg:security.admin_password=admin \
	cfg:auth.anonymous.enabled=true \
	cfg:auth.anonymous.org_role=Viewer \
	>"$LOG_DIR/grafana.log" 2>&1 &
echo $! >"$PID_FILE"

for _ in 1 2 3 4 5 6 7 8 9 10; do
	if http_ready "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/api/health"; then
		break
	fi
	sleep 1
done
pid=$(cat "$PID_FILE")
pids=$(grafana_pids | tr '\n' ' ')
if [ -n "$pids" ]; then
	set -- $pids
	pid=$1
	echo "$pid" >"$PID_FILE"
fi
if ! is_alive "$pid"; then
	echo "trace Grafana failed; see $LOG_DIR/grafana.log" >&2
	exit 1
fi

check_http "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/api/health"

echo "trace Grafana pid=$pid addr=$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT"
echo "http://$TRACE_GRAFANA_ADDR:$TRACE_GRAFANA_PORT/d/rt-trace-stages"
