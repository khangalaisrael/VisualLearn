#!/usr/bin/env bash
# One-time bootstrap for an Oracle Cloud Always Free Ubuntu VM
# (docs/DEPLOY.md). Run on the VM as the default `ubuntu` user:
#   bash scripts/setup-oracle-vm.sh
# Idempotent — safe to re-run.
set -euo pipefail

echo "==> Installing Docker Engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

echo "==> Opening ports 80/443 in the VM's own iptables"
# Oracle's Ubuntu images ship an iptables REJECT rule that blocks
# everything except SSH, *in addition to* the VCN Security List in the
# console. Both layers must allow 80/443 or Let's Encrypt validation and
# all HTTPS traffic silently time out.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
  fi
done
if ! sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT
fi
sudo apt-get install -y netfilter-persistent iptables-persistent >/dev/null
sudo netfilter-persistent save

echo "==> Done. Log out and back in (so the docker group applies), then:"
echo "    cp .env.example .env   # fill in production values — see docs/DEPLOY.md"
echo "    docker compose -f docker-compose.prod.yml up -d --build"
echo "    docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
