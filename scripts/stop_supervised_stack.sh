#!/bin/sh
set -eu

VISIONFIVE=${1:-root@10.42.0.211}
ROCKPI=${2:-root@10.43.0.2}

ssh "$VISIONFIVE" "ssh '$ROCKPI' sh -s" <<'ROCKPI_REMOTE'
set -eu

pids=$(pgrep -x controller-emu 2>/dev/null | tr '\n' ' ' || true)
if [ -z "$pids" ]; then
	echo "controller-emu: not running"
	exit 0
fi

echo "controller-emu: stopping $pids"
kill $pids 2>/dev/null || true
for _ in 1 2 3 4 5; do
	alive=
	for pid in $pids; do
		if kill -0 "$pid" 2>/dev/null; then
			alive="$alive $pid"
		fi
	done
	if [ -z "$alive" ]; then
		echo "controller-emu: stopped"
		exit 0
	fi
	sleep 1
done

echo "controller-emu: killing$alive"
kill -KILL $alive 2>/dev/null || true
ROCKPI_REMOTE

ssh "$VISIONFIVE" sh -s <<'VISIONFIVE_REMOTE'
set -eu

kill_pids()
{
	label=$1
	pids=$2

	if [ -z "$pids" ]; then
		echo "$label: not running"
		return 0
	fi

	echo "$label: stopping $pids"
	kill $pids 2>/dev/null || true
	for _ in 1 2 3 4 5; do
		alive=
		for pid in $pids; do
			if kill -0 "$pid" 2>/dev/null; then
				alive="$alive $pid"
			fi
		done
		if [ -z "$alive" ]; then
			echo "$label: stopped"
			return 0
		fi
		sleep 1
	done

	echo "$label: killing$alive"
	kill -KILL $alive 2>/dev/null || true
}

supervisor_pids=$(pgrep -x alt-rt-supervis 2>/dev/null | tr '\n' ' ' || true)
kill_pids "alt-rt-supervisor" "$supervisor_pids"

runtime_pids=$(ps -eo pid,args | awk '/[B]eremiz_service.py/ { print $1 }' | tr '\n' ' ')
kill_pids "Beremiz_service.py" "$runtime_pids"

rm -f /dev/shm/shmem_input /dev/shm/shmem_output
VISIONFIVE_REMOTE
