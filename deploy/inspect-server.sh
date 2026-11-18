#!/usr/bin/env bash
set -eu
printf 'SYSTEM\n'
cat /etc/os-release | head -6
printf '\nRESOURCES\n'
nproc
free -h
df -h /
printf '\nTOOLS\n'
for tool in docker nginx certbot git python3 psql; do command -v "$tool" || true; done
printf '\nLISTENERS\n'
ss -ltnp
printf '\nWEB CONFIGURATION\n'
ls -la /etc/nginx/sites-enabled /etc/nginx/conf.d /opt 2>/dev/null || true
printf '\nDNS\n'
getent ahostsv4 kongqi.xyz || true
