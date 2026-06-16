#!/bin/sh
set -eu

TARGET=${1:-root@10.42.0.211}
RUNTIME_DIR=${2:-/root/beremiz-runtime/supervised-raw-plc}
BIND_IP=${3:-10.42.0.211}
PORT=${4:-3000}
REMOTE_DIR=${5:-/root/beremiz-stand}
WRAPPER="$RUNTIME_DIR/start_runtime.sh"
COMPAT_EXTENSION="$REMOTE_DIR/scripts/beremiz_runtime_compat_15.py"

ssh "$TARGET" \
	"set -eu; \
	mkdir -p '$RUNTIME_DIR'; \
	cat > '$WRAPPER' <<'EOF'
#!/bin/sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
cd '$RUNTIME_DIR'
exec /usr/bin/python3 /usr/share/beremiz/Beremiz_service.py \
	-i '$BIND_IP' -p '$PORT' -a 1 -x 0 -t 0 -w off \
	-e '$COMPAT_EXTENSION' .
EOF
	chmod +x '$WRAPPER'; \
	ls -l '$WRAPPER'"

echo "Installed supervised runtime wrapper at $TARGET:$WRAPPER"
