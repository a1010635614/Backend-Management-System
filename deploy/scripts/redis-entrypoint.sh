#!/bin/sh
set -eu
case "${REDIS_PASSWORD:-}" in ''|*[!a-zA-Z0-9]*) echo 'REDIS_PASSWORD must be random ASCII letters/digits' >&2; exit 2;; esac
test "${#REDIS_PASSWORD}" -ge 32
umask 077
cat > /tmp/blog-redis.conf <<EOF
bind 0.0.0.0
port 6379
protected-mode yes
requirepass "$REDIS_PASSWORD"
dir /data
appendonly yes
appendfsync always
save ""
maxmemory 64mb
maxmemory-policy noeviction
maxclients 128
tcp-keepalive 60
logfile ""
EOF
exec redis-server /tmp/blog-redis.conf
