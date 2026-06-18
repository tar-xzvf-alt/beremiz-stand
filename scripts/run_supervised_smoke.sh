#!/bin/sh
set -eu

VISIONFIVE=${VISIONFIVE:-${1:-root@10.42.0.211}}
ROCKPI=${ROCKPI:-${2:-root@10.43.0.2}}
RT_TESTER_DIR=${RT_TESTER_DIR:-/home/taranev/work_repos/rt/rt-tester}
ARDUINO_PORT=${ARDUINO_PORT:-/dev/ttyACM0}
RECEIVER_TIMEOUT_SEC=${RECEIVER_TIMEOUT_SEC:-120}
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
EXPECTED_GROUPS=$(param_value auto-stop-groups)

if [ -z "$SMOKE_DB" ]; then
	echo "Smoke params do not define db" >&2
	exit 1
fi

if [ -z "$EXPECTED_GROUPS" ]; then
	EXPECTED_GROUPS=3
fi

if [ "$SKIP_START" != 1 ]; then
	echo "== Start supervised stack =="
	TIMEOUT_US=30000000 "$SCRIPT_DIR/start_supervised_stack.sh" \
		"$VISIONFIVE" "$ROCKPI"
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
		--start \
		--exit-on-stop
)

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

print(f"session={session_id}")
print(f"groups={group_count}")
print(f"latencies={latency_count}")
print(f"latency_min_avg_max_us={min_us} / {avg_us:.2f} / {max_us}")
for event_type, details in events:
    print(f"event={event_type}: {details}")

if group_count != expected_groups:
    raise SystemExit(
        f"Expected {expected_groups} groups, saved {group_count}"
    )
PY
