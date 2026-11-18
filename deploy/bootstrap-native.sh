#!/usr/bin/env bash
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv postgresql certbot
id blog >/dev/null 2>&1 || useradd --system --home-dir /opt/vueblog --shell /usr/sbin/nologin blog
install -d -o blog -g blog -m 750 /opt/vueblog
install -d -m 755 /var/www/certbot
systemctl enable --now postgresql
printf '\nBOOTSTRAP COMPLETE\n'
psql --version
