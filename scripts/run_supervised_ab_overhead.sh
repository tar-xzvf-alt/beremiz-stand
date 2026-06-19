#!/bin/sh
set -eu

VISIONFIVE=${VISIONFIVE:-${1:-root@10.42.0.211}}
ROCKPI=${ROCKPI:-${2:-root@10.43.0.2}}
AB_REPEATS=${AB_REPEATS:-1}
AB_GROUPS=${AB_GROUPS:-2}
AB_PROMETHEUS_URL=${AB_PROMETHEUS_URL:-http://127.0.0.1:9091}
AB_OUT_DIR=${AB_OUT_DIR:-/tmp/rt-supervised-ab-$(date +%Y%m%d-%H%M%S)}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$AB_REPEATS" -lt 1 ]; then
	echo "AB_REPEATS must be >= 1" >&2
	exit 1
fi

mkdir -p "$AB_OUT_DIR"

echo "A/B output: $AB_OUT_DIR"
echo "groups per run: $AB_GROUPS"
echo "repeats per mode: $AB_REPEATS"

run_mode()
{
	mode=$1
	repeat=$2
	log=$AB_OUT_DIR/${repeat}-${mode}.log

	echo
	echo "== A/B run repeat=$repeat mode=$mode =="
	case "$mode" in
	prometheus)
		if TRACE_MODE=prometheus \
		TRACE_PROMETHEUS_URL="$AB_PROMETHEUS_URL" \
		SMOKE_GROUPS="$AB_GROUPS" \
			"$SCRIPT_DIR/run_supervised_smoke.sh" "$VISIONFIVE" "$ROCKPI" \
			>"$log" 2>&1; then
			cat "$log"
		else
			status=$?
			cat "$log"
			exit "$status"
		fi
		;;
	*)
		if TRACE_MODE="$mode" \
		SMOKE_GROUPS="$AB_GROUPS" \
			"$SCRIPT_DIR/run_supervised_smoke.sh" "$VISIONFIVE" "$ROCKPI" \
			>"$log" 2>&1; then
			cat "$log"
		else
			status=$?
			cat "$log"
			exit "$status"
		fi
		;;
	esac
}

repeat=1
while [ "$repeat" -le "$AB_REPEATS" ]; do
	run_mode off "$repeat"
	run_mode jsonl "$repeat"
	run_mode prometheus "$repeat"
	repeat=$((repeat + 1))
done

echo
echo "== A/B summary =="
repeat=1
while [ "$repeat" -le "$AB_REPEATS" ]; do
	for mode in off jsonl prometheus; do
		log=$AB_OUT_DIR/${repeat}-${mode}.log
		printf '%s: ' "$(basename "$log" .log)"
		awk '
			/^trace_mode=/ { trace_mode = $0 }
			/^session=/ { session = $0 }
			/^groups=/ { groups = $0 }
			/^latencies=/ { latencies = $0 }
			/^latency_min_avg_max_us=/ { latency = $0 }
			/^Imported trace metrics:/ { imported = $0 }
			END {
				printf "%s; %s; %s; %s; %s", trace_mode, session, groups, latencies, latency
				if (imported != "") {
					printf "; %s", imported
				}
				printf "\n"
			}
		' "$log"
	done
	repeat=$((repeat + 1))
done
