Name: beremiz-stand-tools
Version: 0.1.0
Release: alt1
Summary: PC-side orchestration tools for the Beremiz RT stand
License: GPLv3
Group: System/Servers
Url: https://altlinux.space/besogon1238/beremiz-stand
BuildArch: noarch
AutoReq: no

BuildRequires: python3 rpm-build-python3
Requires: python3, /bin/sh, openssh-clients, rsync, tar, coreutils, iproute2
Requires: rt-tester-tools >= 0.1.0

Source0: %name-%version.tar

%description
beremiz-stand-tools contains the PC-side helper CLI, profiles and
documentation used to operate the Beremiz supervised RT latency stand.
It does not install PLC runtime projects or deploy target runtime artifacts.

%prep
%setup

%build

%install
install -d %buildroot%_bindir
install -d %buildroot%_datadir/%name/scripts
install -d %buildroot%_datadir/%name/profiles
install -d %buildroot%_sysconfdir/beremiz-stand
install -m644 scripts/_cmd.py scripts/_lib.py scripts/beremiz_runtime_compat_15.py \
    %buildroot%_datadir/%name/scripts/
install -m755 scripts/stand.py scripts/check_runtime_status.py \
    scripts/summarize_ab_overhead.py scripts/*.sh \
    %buildroot%_datadir/%name/scripts/
install -m644 profiles/stand.conf.example \
    %buildroot%_datadir/%name/profiles/stand.conf.example
install -m644 profiles/stand.conf.example \
    %buildroot%_sysconfdir/beremiz-stand/stand.conf

cat > %buildroot%_bindir/beremiz-stand <<'EOF'
#!/bin/sh
root=${BEREMIZ_STAND_ROOT:-/usr/share/beremiz-stand-tools}
export BEREMIZ_STAND_PROFILE=${BEREMIZ_STAND_PROFILE:-/etc/beremiz-stand/stand.conf}
exec /usr/bin/python3 "$root/scripts/stand.py" "$@"
EOF
chmod 755 %buildroot%_bindir/beremiz-stand

%check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/stand.py --help >/dev/null
PYTHONPATH=scripts PYTHONDONTWRITEBYTECODE=1 python3 -c \
    'from pathlib import Path; from _lib import load_profile; load_profile(Path("profiles/stand.conf.example"))'
BEREMIZ_STAND_ROOT=%buildroot%_datadir/%name \
BEREMIZ_STAND_PROFILE=%buildroot%_sysconfdir/beremiz-stand/stand.conf \
PYTHONDONTWRITEBYTECODE=1 \
    %buildroot%_bindir/beremiz-stand --help >/dev/null
test ! -e %buildroot%_datadir/%name/beremiz-project
test ! -e %buildroot%_datadir/%name/.deps
test ! -e %buildroot%_datadir/%name/logs

%files
%_bindir/beremiz-stand
%_datadir/%name/
%config(noreplace) %_sysconfdir/beremiz-stand/stand.conf
%doc README.md QUICKSTART.md GUIDE.md NETWORK.md PACKAGED_SETUP.md ROADMAP.md TEST_PROTOCOL.md

%changelog
* Tue Jul 14 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.0-alt1
- Initial package with PC-side stand orchestration tools.
