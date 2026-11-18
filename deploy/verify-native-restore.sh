#!/usr/bin/env bash
set -euo pipefail
backup=$(find /var/backups/vueblog -maxdepth 1 -type f -name 'blog-????????T??????Z.dump' | sort | tail -1)
test -n "$backup"
testdb="blog_restore_check_$$"
[[ "$testdb" =~ ^blog_restore_check_[0-9]+$ ]] || exit 1
created=false
cleanup() { if "$created"; then runuser -u postgres -- dropdb --if-exists "$testdb"; fi; }
trap cleanup EXIT
runuser -u postgres -- createdb "$testdb"
created=true
# Feed via stdin: backup directory stays readable only by root.
runuser -u postgres -- pg_restore --exit-on-error --no-owner --no-acl --dbname="$testdb" < "$backup"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d "$testdb" <<'SQL'
select version_num from alembic_version;
select count(*) as restored_posts from posts;
select count(*) as restored_users from users;
select count(*) as restored_events from analytics_events;
select count(*) as restored_codes from email_codes;
select count(*) as restored_assets from assets;
SQL
printf 'Restore completed in isolated database; production data was not changed.\n'
