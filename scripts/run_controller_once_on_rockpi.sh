#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
REMOTE_DIR=${3:-/root/device-controller}
IFACE=${4:-end0}
SEQUENCE=${5:-2003}
SENSOR=${6:-600}
THRESHOLD=${7:-500}
FORCED_OUTPUT=${8:-0}
TIMEOUT_MS=${9:-2000}

ssh "$VISIONFIVE" \
	"set -eu; \
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '$ROCKPI' \
		\"cd '$REMOTE_DIR' && ./controller-once -i '$IFACE' \
		--sequence '$SEQUENCE' --sensor '$SENSOR' --threshold '$THRESHOLD' \
		--forced-output '$FORCED_OUTPUT' --timeout-ms '$TIMEOUT_MS'\""
