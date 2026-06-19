#!/bin/sh
set -eu

RUNTIME_DIR=${TRACE_GRAFANA_RUNTIME_DIR:-/tmp/rt-trace-grafana-local}
DATA_DIR=${TRACE_GRAFANA_DATA_DIR:-$RUNTIME_DIR/data}
PID_FILE=$RUNTIME_DIR/grafana.pid

grafana_pids()
{
	ps -eo pid,args | awk -v data="cfg:paths.data=$DATA_DIR" \
		'/[g]rafana/ && index($0, data) { print $1 }'
}

if [ -f "$PID_FILE" ]; then
	pids=$(cat "$PID_FILE")
else
	pids=
fi

live_pids=
for pid in $pids; do
	if kill -0 "$pid" 2>/dev/null; then
		live_pids="$live_pids $pid"
	fi
done

if [ -z "$live_pids" ]; then
	live_pids=$(grafana_pids | tr '\n' ' ')
fi

if [ -z "$live_pids" ]; then
	echo "trace Grafana: not running"
	rm -f "$PID_FILE"
	exit 0
fi

echo "trace Grafana: stopping $live_pids"
kill $live_pids 2>/dev/null || true
for _ in 1 2 3 4 5; do
	alive=
	for pid in $live_pids; do
		if kill -0 "$pid" 2>/dev/null; then
			alive="$alive $pid"
		fi
	done
	if [ -z "$alive" ]; then
		echo "trace Grafana: stopped"
		rm -f "$PID_FILE"
		exit 0
	fi
	sleep 1
done

echo "trace Grafana: killing $alive"
kill -KILL $alive 2>/dev/null || true
rm -f "$PID_FILE"
