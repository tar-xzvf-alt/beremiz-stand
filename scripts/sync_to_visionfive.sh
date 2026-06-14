#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}

ARCHIVE=$(mktemp /tmp/beremiz-stand-transfer.XXXXXX.tgz)
trap 'rm -f "$ARCHIVE"' EXIT

tar \
	--exclude='./.git' \
	--exclude='./.deps' \
	--exclude='./beremiz-project/*/build' \
	--exclude='./beremiz-project/*/psk' \
	--exclude='./beremiz-project/*/psk/*' \
	--exclude='__pycache__' \
	-czf "$ARCHIVE" .

scp -q "$ARCHIVE" "$TARGET:/tmp/beremiz-stand-transfer.tgz"
ssh "$TARGET" \
	"rm -rf '$REMOTE_DIR' && mkdir -p '$REMOTE_DIR' && tar -xzf /tmp/beremiz-stand-transfer.tgz -C '$REMOTE_DIR'"

echo "Synced workspace to $TARGET:$REMOTE_DIR"
