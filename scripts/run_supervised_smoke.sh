#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TRACE_MODE="${TRACE_MODE:-off}"

case "$TRACE_MODE" in
off)
	exec "$SCRIPT_DIR/stand.py" test-smoke
	;;
prometheus)
	exec "$SCRIPT_DIR/stand.py" test-trace
	;;
jsonl)
	echo "TRACE_MODE=jsonl not yet supported by stand.py" >&2
	exit 1
	;;
*)
	echo "Unknown TRACE_MODE: $TRACE_MODE" >&2
	exit 1
	;;
esac
