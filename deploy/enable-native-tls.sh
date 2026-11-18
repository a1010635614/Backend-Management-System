#!/usr/bin/env bash
set -eu
certbot certonly --non-interactive --agree-tos --register-unsafely-without-email --webroot -w /var/www/certbot -d kongqi.xyz
cp -an /etc/nginx/sites-available/vueblog /etc/nginx/sites-available/vueblog.before-tls
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/nginx/sites-available/vueblog')
s=p.read_text()
if 'ssl_certificate ' not in s:
    s=s.replace('    listen 80;','    listen 443 ssl;\n    ssl_certificate /etc/letsencrypt/live/kongqi.xyz/fullchain.pem;\n    ssl_certificate_key /etc/letsencrypt/live/kongqi.xyz/privkey.pem;\n    ssl_protocols TLSv1.2 TLSv1.3;\n    add_header X-Content-Type-Options nosniff always;')
    s+='\nserver {\n listen 80;\n server_name kongqi.xyz;\n location /.well-known/acme-challenge/ { root /var/www/certbot; }\n location / { return 301 https://$host$request_uri; }\n}\n'
    p.write_text(s)
PY
nginx -t
systemctl reload nginx
install -d /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/vueblog-nginx.sh <<'HOOK'
#!/bin/sh
nginx -t && systemctl reload nginx
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/vueblog-nginx.sh
systemctl enable --now certbot.timer
curl -fsS https://kongqi.xyz/api/health
