#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
REMOTE_DIR=${3:-/root/device-controller}
IFACE=${4:-end0}
SEQUENCE=${5:-4000}
TIMEOUT_MS=${6:-1000}
COUNT=${7:-0}
RUN_TIMEOUT=${8:-0}

if [ "$RUN_TIMEOUT" = 0 ]; then
	TIMEOUT_PREFIX=
else
	TIMEOUT_PREFIX="timeout '${RUN_TIMEOUT}s' "
fi

ssh "$VISIONFIVE" \
	"set -eu; \
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '$ROCKPI' \
		\"cd '$REMOTE_DIR' && ${TIMEOUT_PREFIX}./controller-gpio-loop -i '$IFACE' \
		--sequence '$SEQUENCE' --timeout-ms '$TIMEOUT_MS' --count '$COUNT'\""
