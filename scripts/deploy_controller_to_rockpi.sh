#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
REMOTE_DIR=${3:-/root/device-controller}

ARCHIVE=$(mktemp /tmp/device-controller-transfer.XXXXXX.tgz)
trap 'rm -f "$ARCHIVE"' EXIT

tar \
	--exclude='./device-controller/controller-once' \
	--exclude='./device-controller/controller-loop' \
	--exclude='./device-controller/controller-gpio-loop' \
	--mtime='2000-01-01' \
	-czf "$ARCHIVE" device-controller

scp -q "$ARCHIVE" "$VISIONFIVE:/tmp/device-controller-transfer.tgz"
ssh "$VISIONFIVE" \
	"set -eu; \
	scp -q -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
		/tmp/device-controller-transfer.tgz '$ROCKPI:/tmp/device-controller-transfer.tgz'; \
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '$ROCKPI' \
		\"rm -rf '$REMOTE_DIR' && mkdir -p '$REMOTE_DIR' && \
		tar --strip-components=1 -xzf /tmp/device-controller-transfer.tgz -C '$REMOTE_DIR' && \
		find '$REMOTE_DIR' -exec touch {} +\""

echo "Deployed device-controller to $ROCKPI:$REMOTE_DIR via $VISIONFIVE"
