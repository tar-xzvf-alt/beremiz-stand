#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
VISIONFIVE_IFACE=${2:-end0}
VISIONFIVE_ADDR=${3:-10.43.0.1/24}

ssh "$TARGET" \
	"set -eu; \
	ip addr replace '$VISIONFIVE_ADDR' dev '$VISIONFIVE_IFACE'; \
	ip link set '$VISIONFIVE_IFACE' up; \
	ip -o addr show dev '$VISIONFIVE_IFACE'"
