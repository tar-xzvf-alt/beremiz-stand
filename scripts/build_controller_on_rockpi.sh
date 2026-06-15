#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
REMOTE_DIR=${3:-/root/device-controller}
TARGET=${4:-all}

if [ "$TARGET" = all ]; then
	BUILD_CMD="make clean && make && make controller-gpio-loop"
else
	BUILD_CMD="make '$TARGET'"
fi

ssh "$VISIONFIVE" \
	"set -eu; \
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '$ROCKPI' \
		\"cd '$REMOTE_DIR' && $BUILD_CMD\""
