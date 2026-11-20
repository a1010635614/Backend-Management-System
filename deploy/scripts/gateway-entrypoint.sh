#!/bin/sh
set -eu
gateway=$(/bin/busybox ip route show default | awk 'NR==1 {print $3}')
case "$gateway" in ''|*[!0-9.]*) echo 'Unable to identify host proxy gateway' >&2; exit 2;; esac
umask 077
printf 'set_real_ip_from %s;\nset_real_ip_from 127.0.0.1;\n' "$gateway" > /tmp/blog-trusted-proxy.conf
exec nginx -g 'daemon off;'
