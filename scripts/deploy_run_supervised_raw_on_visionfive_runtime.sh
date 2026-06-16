#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
REMOTE_DIR=${2:-/root/beremiz-stand}
RUNTIME_URI=${3:-ERPC://10.42.0.211:3000}

"$(dirname "$0")/deploy_run_direct_raw_on_visionfive_runtime.sh" \
	"$TARGET" "$REMOTE_DIR" "$RUNTIME_URI" beremiz-project/supervised-raw-plc
