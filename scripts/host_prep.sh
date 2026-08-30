#!/usr/bin/env bash
# ==============================================================================
# host_prep.sh — one-time (idempotent) staging host preparation   [Stage 4, T-4.1]
# ==============================================================================
# Target: a fresh Ubuntu 24.04 LTS VPS (2 vCPU / 4 GB / 40 GB SSD), run as root.
#
#   bash host_prep.sh                 # full prep
#   DEPLOY_USER=deploy bash host_prep.sh
#   bash host_prep.sh --check         # report only, change nothing
#
# What it does (every step is safe to re-run):
#   1. apt update + base tooling (curl, git, ufw, jq, openssl, postgresql-client)
#   2. Docker Engine + compose plugin from Docker's official apt repo
#   3. a non-root deploy user in the docker group, with the invoking root
#      SSH keys copied over so you can log straight in
#   4. UFW: deny incoming, allow 22/80/443 only
#   5. unattended-upgrades for security patches
#   6. 2 GB swap file (4 GB RAM + PG16 HNSW index build is tight without it)
#   7. SSH hardening: no root password login, no password auth (keys only)
#
# It NEVER touches the application, .env, or any secret.
# ==============================================================================
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# /etc/os-release is a host file, not a repository input — shellcheck cannot
# follow it, so the three `. /etc/os-release` sources are annotated inline.

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[0;32mOK\033[0m  %s\n' "$*"; }
warn() { printf '    \033[0;33mWARN\033[0m %s\n' "$*"; }
die()  { printf '\n\033[0;31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (sudo bash host_prep.sh)"

if [ "$CHECK_ONLY" -eq 1 ]; then
  log "CHECK ONLY — no changes will be made"
  # shellcheck disable=SC1091
  printf 'os              : %s\n' "$(. /etc/os-release && echo "$PRETTY_NAME")"
  printf 'cpus            : %s\n' "$(nproc)"
  printf 'memory          : %s\n' "$(free -h | awk '/^Mem:/{print $2}')"
  printf 'disk (/)        : %s\n' "$(df -h / | awk 'NR==2{print $4" free of "$2}')"
  printf 'docker          : %s\n' "$(docker --version 2>/dev/null || echo MISSING)"
  printf 'compose plugin  : %s\n' "$(docker compose version 2>/dev/null || echo MISSING)"
  printf 'deploy user     : %s\n' "$(id "$DEPLOY_USER" 2>/dev/null || echo MISSING)"
  printf 'ufw             : %s\n' "$(ufw status 2>/dev/null | head -1 || echo MISSING)"
  printf 'swap            : %s\n' "$(swapon --show=NAME,SIZE --noheadings 2>/dev/null | tr '\n' ' ' || echo none)"
  exit 0
fi

# ---- 0. sanity ---------------------------------------------------------------
log "Host sanity"
# shellcheck disable=SC1091
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || warn "expected Ubuntu, found ${ID:-unknown} — continuing"
CPUS=$(nproc); MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
DISK_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
ok "os=${PRETTY_NAME} cpus=${CPUS} mem=${MEM_MB}MB disk_free=${DISK_GB}GB"
[ "$CPUS" -ge 2 ]      || warn "fewer than 2 vCPU — the G-4.x p95 contract gate may not hold"
[ "$MEM_MB" -ge 3500 ] || warn "less than 4 GB RAM — PG HNSW index build may OOM"
[ "$DISK_GB" -ge 20 ]  || warn "less than 20 GB free — backups + images will fill the disk"

# ---- 1. base packages --------------------------------------------------------
log "Base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl git jq openssl ufw unattended-upgrades \
  postgresql-client-16 cron logrotate >/dev/null
ok "base tooling installed (curl git jq openssl ufw psql cron logrotate)"

# ---- 2. Docker ---------------------------------------------------------------
log "Docker Engine + compose plugin"
if docker compose version >/dev/null 2>&1; then
  ok "already present: $(docker --version), $(docker compose version)"
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker >/dev/null
  ok "installed: $(docker --version), $(docker compose version)"
fi

# Cap journald/container log growth before the first deploy, not after.
if [ ! -f /etc/docker/daemon.json ]; then
  mkdir -p /etc/docker
  cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
JSON
  systemctl restart docker
  ok "docker log rotation configured (10m x 5 per container)"
else
  ok "/etc/docker/daemon.json already present — left untouched"
fi

# ---- 3. deploy user ----------------------------------------------------------
log "Non-root deploy user: ${DEPLOY_USER}"
if id "$DEPLOY_USER" >/dev/null 2>&1; then
  ok "user exists"
else
  adduser --disabled-password --gecos "" "$DEPLOY_USER" >/dev/null
  ok "user created (no password; SSH key only)"
fi
usermod -aG docker "$DEPLOY_USER"
ok "in docker group"

if [ -f /root/.ssh/authorized_keys ]; then
  install -d -m 0700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/${DEPLOY_USER}/.ssh"
  install -m 0600 -o "$DEPLOY_USER" -g "$DEPLOY_USER" \
    /root/.ssh/authorized_keys "/home/${DEPLOY_USER}/.ssh/authorized_keys"
  ok "root SSH keys copied to ${DEPLOY_USER} ($(wc -l < /root/.ssh/authorized_keys) key line(s))"
else
  warn "no /root/.ssh/authorized_keys — add a key for ${DEPLOY_USER} before hardening SSH"
fi

# ---- 4. firewall -------------------------------------------------------------
log "UFW firewall"
ufw --force default deny incoming >/dev/null
ufw --force default allow outgoing >/dev/null
ufw allow 22/tcp  >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status verbose | sed 's/^/    /'
ok "only 22/80/443 reachable (Postgres and Redis are never published to the host)"

# ---- 5. unattended upgrades --------------------------------------------------
log "Unattended security upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'CONF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
CONF
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
ok "enabled"

# ---- 6. swap -----------------------------------------------------------------
log "Swap (${SWAP_SIZE})"
if swapon --show=NAME --noheadings | grep -q .; then
  ok "swap already active: $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
else
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ok "created and enabled /swapfile (${SWAP_SIZE})"
fi

# ---- 7. SSH hardening --------------------------------------------------------
log "SSH hardening"
if [ -f "/home/${DEPLOY_USER}/.ssh/authorized_keys" ]; then
  cat > /etc/ssh/sshd_config.d/99-staging-hardening.conf <<'CONF'
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
CONF
  sshd -t && systemctl reload ssh
  ok "password auth disabled, root password login disabled (keys still work)"
else
  warn "skipped — no authorized_keys for ${DEPLOY_USER}; you would lock yourself out"
fi

# ---- done --------------------------------------------------------------------
log "HOST PREP COMPLETE"
cat <<EOF
    Next:
      su - ${DEPLOY_USER}
      git clone https://github.com/AliNaderiii/Smart-Interior-Decor-Recommendation-Platform.git app
      cd app && cp .env.staging.example .env && chmod 600 .env && \$EDITOR .env
      ./scripts/deploy_staging.sh

    Verify this run:  bash host_prep.sh --check
EOF
