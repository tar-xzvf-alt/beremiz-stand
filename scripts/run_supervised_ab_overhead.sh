#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

AB_REPEATS="${AB_REPEATS:-1}"
AB_GROUPS="${AB_GROUPS:-2}"
AB_OUT_DIR="${AB_OUT_DIR:-}"

args="--ab-repeats $AB_REPEATS --ab-groups $AB_GROUPS"
if [ -n "$AB_OUT_DIR" ]; then
    args="$args --ab-output $AB_OUT_DIR"
fi

# shellcheck disable=SC2086
exec "$SCRIPT_DIR/stand.py" test-ab $args
