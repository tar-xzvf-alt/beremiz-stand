#!/bin/sh
set -eu

RUNTIME_DIR=${TRACE_PROMETHEUS_RUNTIME_DIR:-/tmp/rt-trace-prometheus-local}

stop_pid_file()
{
	label=$1
	pid_file=$2

	if [ ! -f "$pid_file" ]; then
		echo "$label: not running"
		return 0
	fi

	pid=$(cat "$pid_file")
	if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
		echo "$label: stale pid file"
		rm -f "$pid_file"
		return 0
	fi

	echo "$label: stopping pid=$pid"
	kill "$pid" 2>/dev/null || true
	for _ in 1 2 3 4 5; do
		if ! kill -0 "$pid" 2>/dev/null; then
			echo "$label: stopped"
			rm -f "$pid_file"
			return 0
		fi
		sleep 1
	done

	echo "$label: killing pid=$pid"
	kill -KILL "$pid" 2>/dev/null || true
	rm -f "$pid_file"
}

stop_pid_file "trace Prometheus" "$RUNTIME_DIR/prometheus.pid"
stop_pid_file "RockPI tunnel" "$RUNTIME_DIR/rockpi-tunnel.pid"
stop_pid_file "VisionFive tunnel" "$RUNTIME_DIR/visionfive-tunnel.pid"
