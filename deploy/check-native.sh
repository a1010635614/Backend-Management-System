#!/usr/bin/env bash
set -eu
printf 'SERVICES\n'
systemctl is-active vueblog postgresql nginx
printf '\nDATABASE\n'
runuser -u postgres -- psql -Atc "select version();"
printf '\nRESOURCES\n'
free -h
printf '\nLISTENERS\n'
ss -ltn | grep -E ':(22|80|443|5432|8000)\b'
printf '\nHTTP/HTTPS\n'
curl -sSI http://kongqi.xyz | head -5
curl -fsS https://kongqi.xyz/api/health
printf '\nCERTIFICATES\n'
certbot certificates
printf '\nRENEWAL\n'
systemctl is-enabled certbot.timer
certbot renew --dry-run
