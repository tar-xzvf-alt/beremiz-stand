#!/bin/sh
set -eu

VISIONFIVE=${VISIONFIVE:-${1:-root@10.42.0.211}}
RT_TESTER_DIR=${RT_TESTER_DIR:-/home/taranev/work_repos/rt/rt-tester}
PROMETHEUS_BIN=${PROMETHEUS_BIN:-/bin/prometheus}
TRACE_PROMETHEUS_ADDR=${TRACE_PROMETHEUS_ADDR:-127.0.0.1:9091}
VISIONFIVE_TUNNEL_PORT=${VISIONFIVE_TUNNEL_PORT:-19201}
ROCKPI_TUNNEL_PORT=${ROCKPI_TUNNEL_PORT:-19202}
RUNTIME_DIR=${TRACE_PROMETHEUS_RUNTIME_DIR:-/tmp/rt-trace-prometheus-local}
DATA_DIR=${TRACE_PROMETHEUS_DATA_DIR:-$RUNTIME_DIR/data}
RETENTION=${TRACE_PROMETHEUS_RETENTION:-2h}
CONFIG=${TRACE_PROMETHEUS_CONFIG:-$RT_TESTER_DIR/prometheus/trace-prometheus-local-tunnel.yml}

VF_PID=$RUNTIME_DIR/visionfive-tunnel.pid
RP_PID=$RUNTIME_DIR/rockpi-tunnel.pid
PROM_PID=$RUNTIME_DIR/prometheus.pid

is_alive()
{
	pid=$1
	[ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start_tunnel()
{
	label=$1
	pid_file=$2
	forward=$3
	log_file=$RUNTIME_DIR/$label.log

	if [ -f "$pid_file" ]; then
		pid=$(cat "$pid_file")
		if is_alive "$pid"; then
			echo "$label tunnel already running pid=$pid"
			return 0
		fi
		rm -f "$pid_file"
	fi

	nohup ssh -N -o ExitOnForwardFailure=yes -L "$forward" "$VISIONFIVE" \
		>"$log_file" 2>&1 &
	echo $! >"$pid_file"
	sleep 1
	pid=$(cat "$pid_file")
	if ! is_alive "$pid"; then
		echo "$label tunnel failed; see $log_file" >&2
		exit 1
	fi
	echo "$label tunnel pid=$pid forward=$forward"
}

check_http()
{
	url=$1
	python3 - "$url" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
try:
    urllib.request.urlopen(url, timeout=5).read(1)
except Exception as exc:
    raise SystemExit(f'{url}: {exc}')
PY
}

check_optional_http()
{
	url=$1
	if ! python3 - "$url" <<'PY'
import sys
import urllib.request

try:
    urllib.request.urlopen(sys.argv[1], timeout=5).read(1)
except Exception:
    raise SystemExit(1)
PY
	then
		echo "trace exporter is not ready at $url; normal before smoke starts" >&2
	fi
}

if [ ! -x "$PROMETHEUS_BIN" ]; then
	echo "Prometheus binary not found: $PROMETHEUS_BIN" >&2
	exit 1
fi

if [ ! -f "$CONFIG" ]; then
	echo "Prometheus config not found: $CONFIG" >&2
	exit 1
fi

mkdir -p "$RUNTIME_DIR" "$DATA_DIR"

start_tunnel "visionfive" "$VF_PID" \
	"$VISIONFIVE_TUNNEL_PORT:127.0.0.1:9201"
start_tunnel "rockpi" "$RP_PID" \
	"$ROCKPI_TUNNEL_PORT:10.43.0.2:9201"

if [ -f "$PROM_PID" ]; then
	pid=$(cat "$PROM_PID")
	if is_alive "$pid"; then
		echo "trace Prometheus already running pid=$pid"
	else
		rm -f "$PROM_PID"
	fi
fi

if [ ! -f "$PROM_PID" ]; then
	nohup "$PROMETHEUS_BIN" \
		--config.file="$CONFIG" \
		--storage.tsdb.path="$DATA_DIR" \
		--web.listen-address="$TRACE_PROMETHEUS_ADDR" \
		--storage.tsdb.retention.time="$RETENTION" \
		>"$RUNTIME_DIR/prometheus.log" 2>&1 &
	echo $! >"$PROM_PID"
	sleep 2
	pid=$(cat "$PROM_PID")
	if ! is_alive "$pid"; then
		echo "trace Prometheus failed; see $RUNTIME_DIR/prometheus.log" >&2
		exit 1
	fi
	echo "trace Prometheus pid=$pid addr=$TRACE_PROMETHEUS_ADDR"
fi

check_http "http://$TRACE_PROMETHEUS_ADDR/-/ready"
check_optional_http "http://127.0.0.1:$VISIONFIVE_TUNNEL_PORT/metrics"
check_optional_http "http://127.0.0.1:$ROCKPI_TUNNEL_PORT/metrics"

echo "TRACE_PROMETHEUS_URL=http://$TRACE_PROMETHEUS_ADDR"
