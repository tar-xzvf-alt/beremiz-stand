#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
REMOTE_DIR=${3:-/root/device-controller}
IFACE=${4:-end0}
SEQUENCE=${5:-3000}
COUNT=${6:-6}
PERIOD_MS=${7:-200}
TIMEOUT_MS=${8:-2000}

ssh "$VISIONFIVE" \
	"set -eu; \
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '$ROCKPI' \
		\"cd '$REMOTE_DIR' && ./controller-loop -i '$IFACE' \
		--sequence '$SEQUENCE' --count '$COUNT' --period-ms '$PERIOD_MS' \
		--timeout-ms '$TIMEOUT_MS'\""
