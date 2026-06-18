#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}
ERPC_URL=${ERPC_URL:-ERPC://10.42.0.211:3000}

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

echo "== ERPC runtime =="
timeout 10s /usr/bin/python3 "$SCRIPT_DIR/check_runtime_status.py" "$ERPC_URL"

echo
echo "== VisionFive processes =="
ssh "$VISIONFIVE" sh -s <<'VISIONFIVE_REMOTE'
set -eu

failed=0

print_processes()
{
	label=$1
	pids=$2

	if [ -z "$pids" ]; then
		echo "$label: missing"
		failed=1
		return
	fi

	pid_csv=$(printf '%s\n' $pids | paste -sd, -)
	echo "$label: $pids"
	ps -o pid,cls,rtprio,pri,psr,comm,args -p "$pid_csv"
	ps -L -o pid,tid,cls,rtprio,pri,psr,comm -p "$pid_csv"
	for pid in $pids; do
		awk '/Cpus_allowed_list/ { print "pid " pid " Cpus_allowed_list=" $2 }' \
			pid="$pid" "/proc/$pid/status"
		for status in /proc/$pid/task/*/status; do
			[ -e "$status" ] || continue
			tid=${status%/status}
			tid=${tid##*/}
			awk '/Cpus_allowed_list/ { print "tid " tid " Cpus_allowed_list=" $2 }' \
				tid="$tid" "$status"
		done
	done
}

supervisor_pids=$(pgrep -x alt-rt-supervis 2>/dev/null | tr '\n' ' ' || true)
runtime_pids=$(ps -eo pid,args | awk '/[B]eremiz_service.py/ { print $1 }' | tr '\n' ' ')

print_processes "alt-rt-supervisor" "$supervisor_pids"
print_processes "Beremiz_service.py" "$runtime_pids"

for slot in /dev/shm/shmem_input /dev/shm/shmem_output; do
	if [ -e "$slot" ]; then
		ls -l "$slot"
	else
		echo "$slot: missing"
		failed=1
	fi
done

exit "$failed"
VISIONFIVE_REMOTE

echo
echo "== RockPI processes =="
ssh "$VISIONFIVE" "ssh '$ROCKPI' sh -s" <<'ROCKPI_REMOTE'
set -eu

pids=$(pgrep -x controller-emu 2>/dev/null | tr '\n' ' ' || true)
if [ -z "$pids" ]; then
	echo "controller-emu: missing"
	exit 1
fi

pid_csv=$(printf '%s\n' $pids | paste -sd, -)
echo "controller-emu: $pids"
ps -o pid,cls,rtprio,pri,psr,comm,args -p "$pid_csv"
ps -L -o pid,tid,cls,rtprio,pri,psr,comm -p "$pid_csv"
for pid in $pids; do
	awk '/Cpus_allowed_list/ { print "pid " pid " Cpus_allowed_list=" $2 }' \
		pid="$pid" "/proc/$pid/status"
	for status in /proc/$pid/task/*/status; do
		[ -e "$status" ] || continue
		tid=${status%/status}
		tid=${tid##*/}
		awk '/Cpus_allowed_list/ { print "tid " tid " Cpus_allowed_list=" $2 }' \
			tid="$tid" "$status"
	done
done
ROCKPI_REMOTE
