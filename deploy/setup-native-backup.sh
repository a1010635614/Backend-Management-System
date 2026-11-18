#!/usr/bin/env bash
set -eu
install -d -m 700 /var/backups/vueblog
cat > /usr/local/sbin/vueblog-backup <<'BACKUP'
#!/usr/bin/env bash
set -euo pipefail
umask 077
exec 9>/var/backups/vueblog/.backup.lock
flock -n 9 || exit 1
output="/var/backups/vueblog/blog-$(date -u +%Y%m%dT%H%M%SZ).dump"
trap 'rm -f -- "$output.partial"' EXIT
runuser -u postgres -- pg_dump --format=custom --no-owner --no-acl blog > "$output.partial"
pg_restore --list "$output.partial" >/dev/null
mv -- "$output.partial" "$output"
# Only backups made by this script inside its fixed directory are expired.
find /var/backups/vueblog -maxdepth 1 -type f -name 'blog-????????T??????Z.dump' -mtime +7 -delete
printf '%s\n' "$output"
BACKUP
chmod 750 /usr/local/sbin/vueblog-backup
cat > /etc/systemd/system/vueblog-backup.service <<'UNIT'
[Unit]
Description=VueBlog PostgreSQL backup
After=postgresql.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vueblog-backup
UMask=0077
UNIT
cat > /etc/systemd/system/vueblog-backup.timer <<'UNIT'
[Unit]
Description=Daily VueBlog backup
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
RandomizedDelaySec=300
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now vueblog-backup.timer
systemctl start vueblog-backup.service
systemctl is-active vueblog-backup.timer
find /var/backups/vueblog -maxdepth 1 -type f -name '*.dump' -printf '%f %s bytes\n'
