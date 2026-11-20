#!/usr/bin/env bash
# Prepara una VM Ubuntu (Oracle Cloud Always Free) para correr el bot.
# Uso, dentro de la VM:  bash deploy/setup-vm.sh
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Córrelo con tu usuario normal (usa sudo internamente)." >&2
  exit 1
fi

echo "==> Actualizando el sistema"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

echo "==> Instalando Docker, Compose, git y actualizaciones automáticas de seguridad"
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker.io docker-compose-v2 git unattended-upgrades iptables-persistent sqlite3 curl
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Abriendo puertos 80 y 443 en el firewall interno de la VM"
# Las imágenes Ubuntu de Oracle traen una regla REJECT en iptables: hay que permitir
# 80/443 ANTES de ella (además de abrirlos en la Security List de la VCN).
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 5 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  fi
done
sudo netfilter-persistent save

echo "==> Memoria swap (necesaria en VMs de 1 GB)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> Respaldo diario de la base de datos (03:30 hora del servidor)"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CRON_LINE="30 3 * * * bash $REPO_DIR/deploy/backup.sh >> $REPO_DIR/data/backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'deploy/backup.sh' ; echo "$CRON_LINE" ) | crontab -

echo
echo "Listo. Cierra la sesión SSH y vuelve a entrar (para usar docker sin sudo)."
echo "Después: crea el .env (ver docs/despliegue.md) y corre: bash deploy/update.sh"
