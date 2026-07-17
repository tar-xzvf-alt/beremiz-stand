# VisionFive 2 + RockPI 4 Stand Network

This document describes the current lab stand network and the recovery commands
needed to keep both SBCs reachable over SSH and connected to the internet.

## Topology

```text
Internet/VPN/Wi-Fi
  |
PC
  default route: tun0, fallback Wi-Fi wlp0s20f3
  enp2s0: 10.42.0.1/24
  route: 10.43.0.0/24 via 10.42.0.211 dev enp2s0
  NAT: 10.42.0.0/24 and 10.43.0.0/24 -> tun0 or wlp0s20f3
  |
VisionFive 2
  SSH: root@10.42.0.211
  end1: 10.42.0.211/24
  end0: 10.43.0.1/24
  default route: 10.42.0.1 via end1
  IPv4 forwarding: enabled
  |
RockPI 4
  SSH: root@10.43.0.2
  end0: 10.43.0.2/24
  default route: 10.43.0.1 via end0

Arduino Mega is connected to VisionFive 2 GPIO for standalone GPIO testing.
```

## Current Verified State

Verified again on 2026-07-17:

```bash
ssh root@10.42.0.211 true
ssh root@10.43.0.2 true
ssh -J root@10.42.0.211 root@10.43.0.2 true
```

Internet checks that passed on both boards:

```bash
getent hosts altlinux.org
curl -I --connect-timeout 8 https://www.altlinux.org
```

ICMP to public addresses is not a reliable check in this environment: the PC
itself did not receive replies from `8.8.8.8`. Use DNS and HTTP/HTTPS checks.

## PC Setup

The wired stand connection must stay static and must not become the PC default
route:

```bash
nmcli connection modify 'Проводное подключение 1' \
  connection.interface-name enp2s0 \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses 10.42.0.1/24 \
  ipv4.routes '10.43.0.0/24 10.42.0.211' \
  ipv4.gateway '' \
  ipv4.never-default yes \
  ipv6.method ignore
nmcli connection up 'Проводное подключение 1' ifname enp2s0
```

Enable forwarding persistently:

```bash
sudo tee /etc/sysctl.d/99-rt-stand-forward.conf >/dev/null <<'EOF'
net.ipv4.ip_forward = 1
EOF
sudo /sbin/sysctl -p /etc/sysctl.d/99-rt-stand-forward.conf
```

NAT is handled by nftables. The active persistent file is
`/etc/nftables/nftables.nft`. A backup was created before the first stand NAT
change as `/etc/nftables/nftables.nft.rt-stand-backup-*`.

Expected NAT section:

```nft
table ip rt_stand_nat {
  chain postrouting {
    type nat hook postrouting priority srcnat; policy accept;
    ip saddr { 10.42.0.0/24, 10.43.0.0/24 } oifname { "tun0", "wlp0s20f3" } masquerade
  }
}
```

Apply and enable nftables:

```bash
sudo /sbin/nft -f /etc/nftables/nftables.nft
sudo systemctl enable --now nftables.service
```

PC checks:

```bash
ip address show dev enp2s0
ip route get 10.42.0.211
ip route get 10.43.0.2
sudo /sbin/sysctl -n net.ipv4.ip_forward
sudo /sbin/nft list table ip rt_stand_nat
```

## VisionFive 2 Setup

VisionFive 2 connects the PC segment to the RockPI segment.

Restore interface profiles:

```bash
ssh root@10.42.0.211 '
nmcli connection modify end1 \
  connection.interface-name end1 \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses 10.42.0.211/24 \
  ipv4.gateway 10.42.0.1 \
  ipv4.dns "8.8.8.8 1.1.1.1" \
  ipv4.ignore-auto-dns yes \
  ipv4.never-default no \
  ipv6.method disabled
nmcli connection modify end0-static \
  connection.interface-name end0 \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses 10.43.0.1/24 \
  ipv4.never-default yes \
  ipv6.method disabled
ip route replace default via 10.42.0.1 dev end1
sysctl -w net.ipv4.ip_forward=1
printf "%s\n" "net.ipv4.ip_forward = 1" > /etc/sysctl.d/99-rt-stand-forward.conf
printf "%s\n" "nameserver 8.8.8.8" "nameserver 1.1.1.1" > /etc/resolv.conf
'
```

Checks:

```bash
ssh root@10.42.0.211 'ip -4 address show; ip route show; sysctl net.ipv4.ip_forward'
ssh root@10.42.0.211 'getent hosts altlinux.org'
ssh root@10.42.0.211 'curl -I --connect-timeout 8 https://www.altlinux.org'
```

## RockPI 4 Setup

RockPI is downstream from VisionFive 2.

Restore interface profile:

```bash
ssh root@10.43.0.2 '
nmcli connection modify end0-static \
  connection.interface-name end0 \
  connection.autoconnect yes \
  ipv4.method manual \
  ipv4.addresses 10.43.0.2/24 \
  ipv4.gateway 10.43.0.1 \
  ipv4.routes "10.42.0.0/24 10.43.0.1" \
  ipv4.dns "8.8.8.8 1.1.1.1" \
  ipv4.ignore-auto-dns yes \
  ipv4.never-default no \
  ipv6.method disabled
ip route replace default via 10.43.0.1 dev end0
printf "%s\n" "nameserver 8.8.8.8" "nameserver 1.1.1.1" > /etc/resolv.conf
'
```

Checks:

```bash
ssh root@10.43.0.2 'ip -4 address show; ip route show'
ssh root@10.43.0.2 'getent hosts altlinux.org'
ssh root@10.43.0.2 'curl -I --connect-timeout 8 https://www.altlinux.org'
```

## SSH Access

Direct access from the PC:

```bash
ssh root@10.42.0.211
ssh root@10.43.0.2
```

RockPI access through VisionFive 2, useful if direct routing is broken:

```bash
ssh -J root@10.42.0.211 root@10.43.0.2
```

If SSH reports a changed RockPI host key, refresh only that host entry:

```bash
ssh-keygen -R 10.43.0.2
ssh -o StrictHostKeyChecking=accept-new root@10.43.0.2 true
```

## Time Sync

Incorrect board clocks can break TLS certificate validation even when networking
works. Restore board time from the PC before HTTPS/package checks:

```bash
ts=$(date +%s)
ssh root@10.42.0.211 "date -u -s '@$ts' >/dev/null; timedatectl set-ntp true 2>/dev/null || true"
ssh root@10.43.0.2 "date -u -s '@$ts' >/dev/null; timedatectl set-ntp true 2>/dev/null || true"
```

If DNS resolves names but `curl` or `apt-get` reports certificate validation
errors, compare `date -u` on the PC and both boards before changing forwarding
or NAT. This was the cause of the apparent internet outage on 2026-07-17: PC
forwarding and nftables NAT were already active, while both board clocks were
months or years behind.

## Final Acceptance Checklist

Run this before stand work:

```bash
ssh root@10.42.0.211 true
ssh root@10.43.0.2 true
ssh -J root@10.42.0.211 root@10.43.0.2 true
ssh root@10.42.0.211 'getent hosts altlinux.org && curl -I --connect-timeout 8 https://www.altlinux.org'
ssh root@10.43.0.2 'getent hosts altlinux.org && curl -I --connect-timeout 8 https://www.altlinux.org'
```
