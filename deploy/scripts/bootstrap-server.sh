#!/usr/bin/env bash
# Docker official repository, or explicitly selected Ubuntu signed packages.
set -euo pipefail
test "$(id -u)" = 0 || { echo 'Run as root'; exit 2; }
. /etc/os-release
test "$ID" = ubuntu || { echo 'This bootstrap supports Ubuntu'; exit 2; }
exec 9>/var/lock/blog-fullstack-bootstrap.lock
flock -n 9 || { echo 'Another bootstrap is running'; exit 1; }
if command -v docker >/dev/null; then
  docker version --format '{{.Server.Version}}'
  docker compose version
  echo 'Existing Docker installation kept.'
  exit 0
fi
for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    echo "Existing conflicting package needs inspection: $package"
    exit 2
  fi
done
free_bytes=$(df -B1 --output=avail /var | tail -1 | tr -d ' ')
test "$free_bytes" -gt 5368709120 || { echo 'At least 5 GiB free disk is required'; exit 2; }
install -d -m 0750 /var/lib/blog-fullstack
memory_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
swap_kib=$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)
if [[ "$memory_kib" -lt 1572864 && "$swap_kib" = 0 ]]; then
  swapfile=/var/lib/blog-fullstack/swapfile
  test ! -e "$swapfile" || { echo 'Existing swap path needs inspection'; exit 2; }
  umask 077
  fallocate -l 1G "$swapfile"
  chmod 0600 "$swapfile"
  mkswap "$swapfile" >/dev/null
  swapon "$swapfile"
  printf '%s\n' "$swapfile none swap defaults,nofail 0 0" >> /etc/fstab
  echo 'Enabled 1 GiB swap for the small-memory host.'
fi
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get -o DPkg::Lock::Timeout=120 update --error-on=any
apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends ca-certificates curl
if [[ "${BLOG_DOCKER_SOURCE:-official}" = ubuntu ]]; then
  echo 'Installing Docker from Ubuntu signed updates/security repositories.'
  apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends docker.io docker-compose-v2 docker-buildx
else
install -d -m 0755 /etc/apt/keyrings
if [[ -e /etc/apt/sources.list.d/docker.sources || -e /etc/apt/sources.list.d/docker.list ]]; then
  echo 'Existing Docker repository configuration needs inspection.'
  exit 2
fi
curl -fsSL --connect-timeout 10 --max-time 90 --retry 2 \
  https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get -o DPkg::Lock::Timeout=120 update --error-on=any
apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
systemctl is-active --quiet docker
docker version --format 'Docker server {{.Server.Version}}'
docker compose version
systemctl is-active vueblog nginx postgresql
echo 'Docker is ready; existing blog service configuration was not changed.'
