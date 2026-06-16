#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}

"$(dirname "$0")/build_direct_raw_on_visionfive.sh" \
	"$TARGET" "$REMOTE_DIR" beremiz-project/supervised-raw-plc
