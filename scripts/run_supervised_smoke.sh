#!/bin/sh
set -eu

VISIONFIVE=${VISIONFIVE:-${1:-root@10.42.0.211}}
ROCKPI=${ROCKPI:-${2:-root@10.43.0.2}}
RT_TESTER_DIR=${RT_TESTER_DIR:-/home/taranev/work_repos/rt/rt-tester}
ARDUINO_PORT=${ARDUINO_PORT:-/dev/ttyACM0}
RECEIVER_TIMEOUT_SEC=${RECEIVER_TIMEOUT_SEC:-120}
SMOKE_GROUPS=${SMOKE_GROUPS:-3}
SUPERVISOR_BIN=${SUPERVISOR_BIN:-/root/rt-supervisor/Build/src/alt-rt-supervisor}
CONTROLLER_BIN=${CONTROLLER_BIN:-/root/rt-supervisor/Build/src/controller-emu}
SESSION_ID=${SESSION_ID:-}
TRACE_PROMETHEUS_URL=${TRACE_PROMETHEUS_URL:-}
TRACE_PROMETHEUS_SETTLE_SEC=${TRACE_PROMETHEUS_SETTLE_SEC:-2}
SKIP_START=${SKIP_START:-0}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
RECEIVER_DIR=$RT_TESTER_DIR/src/pc-receiver
SMOKE_PARAMS=${SMOKE_PARAMS:-$RECEIVER_DIR/measurement-supervised-smoke.conf}

if [ ! -f "$SMOKE_PARAMS" ]; then
	echo "Missing smoke params: $SMOKE_PARAMS" >&2
	exit 1
fi

param_value()
{
	key=$1
	awk -F= -v key="$key" '
		$1 ~ "^[[:space:]]*" key "[[:space:]]*$" {
			value = $2
			sub(/#.*/, "", value)
			gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
			print value
			exit
		}
	' "$SMOKE_PARAMS"
}

SMOKE_DB=$(param_value db)
MEASUREMENTS_PER_GROUP=$(param_value measurements-per-group)
EXPECTED_GROUPS=$SMOKE_GROUPS

if [ -z "$SESSION_ID" ]; then
	SESSION_ID=$(python3 - <<'PY'
import random
print(random.randint(100000, 999999))
PY
)
fi

if [ -z "$SMOKE_DB" ]; then
	echo "Smoke params do not define db" >&2
	exit 1
fi

if [ "$SMOKE_GROUPS" -lt 1 ]; then
	echo "SMOKE_GROUPS must be >= 1" >&2
	exit 1
fi

if [ -z "$MEASUREMENTS_PER_GROUP" ]; then
	echo "Smoke params do not define measurements-per-group" >&2
	exit 1
fi

if [ "$SKIP_START" != 1 ]; then
	echo "== Start supervised stack =="
	RT_TRACE_SESSION_ID="$SESSION_ID" \
	RT_TRACE_MEASUREMENTS_PER_GROUP="$MEASUREMENTS_PER_GROUP" \
		TIMEOUT_US=30000000 "$SCRIPT_DIR/start_supervised_stack.sh" \
		"$VISIONFIVE" "$ROCKPI" "$SUPERVISOR_BIN" "$CONTROLLER_BIN"
	echo
fi

echo "== Check supervised stack =="
"$SCRIPT_DIR/check_supervised_stack.sh" "$VISIONFIVE" "$ROCKPI"

echo
echo "== Run receiver smoke =="
rm -f "$SMOKE_DB" "$SMOKE_DB-shm" "$SMOKE_DB-wal"
(
	cd "$RECEIVER_DIR"
	timeout "${RECEIVER_TIMEOUT_SEC}s" python3 receiver.py \
		--params "$SMOKE_PARAMS" \
		--port "$ARDUINO_PORT" \
		--session-id "$SESSION_ID" \
		--groups "$SMOKE_GROUPS" \
		--start \
		--exit-on-stop
)

if [ -n "$TRACE_PROMETHEUS_URL" ]; then
	echo
	echo "== Import trace metrics =="
	sleep "$TRACE_PROMETHEUS_SETTLE_SEC"
	(
		cd "$RECEIVER_DIR"
		python3 import_trace_metrics.py "$SMOKE_DB" "$SESSION_ID" \
			--prometheus-url "$TRACE_PROMETHEUS_URL"
	)
fi

echo
echo "== Smoke database summary =="
python3 - "$SMOKE_DB" "$EXPECTED_GROUPS" <<'PY'
import sqlite3
import sys

db_path = sys.argv[1]
expected_groups = int(sys.argv[2])

with sqlite3.connect(db_path) as conn:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT session_id, COUNT(*)
        FROM groups
        GROUP BY session_id
        ORDER BY MAX(id) DESC
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if row is None:
        raise SystemExit("No groups saved")

    session_id, group_count = row
    cur.execute(
        """
        SELECT COUNT(*), MIN(l.latency_us), AVG(l.latency_us), MAX(l.latency_us)
        FROM latencies l
        JOIN groups g ON g.id = l.group_id
        WHERE g.session_id = ?
        """,
        (session_id,),
    )
    latency_count, min_us, avg_us, max_us = cur.fetchone()

    cur.execute(
        """
        SELECT event_type, details
        FROM events
        WHERE session_id = ?
        ORDER BY id
        """,
        (session_id,),
    )
    events = cur.fetchall()

    cur.execute(
        """
        SELECT host, stage, COUNT(*), AVG(avg_us), MAX(max_us)
        FROM trace_group_metrics
        WHERE session_id = ?
        GROUP BY host, stage
        ORDER BY host, stage
        """,
        (session_id,),
    )
    trace_rows = cur.fetchall()

print(f"session={session_id}")
print(f"groups={group_count}")
print(f"latencies={latency_count}")
print(f"latency_min_avg_max_us={min_us} / {avg_us:.2f} / {max_us}")
for event_type, details in events:
    print(f"event={event_type}: {details}")
for host, stage, groups, avg_us, max_us in trace_rows:
    print(
        f"trace={host}/{stage}: groups={groups} "
        f"avg_us={avg_us:.2f} max_us={max_us:.2f}"
    )

if group_count != expected_groups:
    raise SystemExit(
        f"Expected {expected_groups} groups, saved {group_count}"
    )
PY
