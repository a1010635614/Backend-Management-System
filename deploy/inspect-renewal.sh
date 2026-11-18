#!/usr/bin/env bash
set -eu
ps -eo pid,etime,args | grep '[c]ertbot renew' || true
grep -E 'sleep|Timeout|timed out|failed|success' /var/log/letsencrypt/letsencrypt.log | tail -6 || true
tail -15 /var/log/letsencrypt/letsencrypt.log
