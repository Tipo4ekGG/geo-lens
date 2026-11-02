#!/usr/bin/env bash
set -euo pipefail
# Restrict only the dedicated tool subnet. Host API and other Docker networks are unaffected.
for destination in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10 127.0.0.0/8; do
 iptables -C DOCKER-USER -s 172.30.80.0/24 -d "$destination" -j REJECT 2>/dev/null || iptables -I DOCKER-USER 1 -s 172.30.80.0/24 -d "$destination" -j REJECT
done
