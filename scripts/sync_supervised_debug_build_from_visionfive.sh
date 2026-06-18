#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
PROJECT=beremiz-project/supervised-raw-plc

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
LOCAL_PROJECT=$REPO_DIR/$PROJECT

if [ ! -d "$LOCAL_PROJECT" ]; then
	echo "Local project not found: $LOCAL_PROJECT" >&2
	exit 1
fi

rm -rf "$LOCAL_PROJECT/build"
scp -r "$TARGET:$REMOTE_DIR/$PROJECT/build" "$LOCAL_PROJECT/"

printf 'Synced GUI debug build artifacts to %s/build\n' "$LOCAL_PROJECT"
printf 'Open GUI with: beremiz %s\n' "$LOCAL_PROJECT"
