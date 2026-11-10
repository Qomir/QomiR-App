#!/usr/bin/env bash
# Installation de Docker + préparation du serveur (Ubuntu 22.04/24.04, x86_64 ou ARM64 Oracle).
# Usage : bash scripts/install_ubuntu.sh
set -euo pipefail

echo "==> Mise à jour du système"
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl git ufw fail2ban unattended-upgrades

echo "==> Installation de Docker (script officiel)"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"
sudo systemctl enable --now docker          # Docker (et donc le bot) redémarre au boot

echo "==> Pare-feu : SSH uniquement (FreqUI passe par le tunnel SSH)"
sudo ufw allow OpenSSH
sudo ufw --force enable

echo "==> Mises à jour de sécurité automatiques"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Horloge (Binance rejette les requêtes si l'heure dérive)"
sudo timedatectl set-ntp true

echo "==> Préparation du projet"
cd "$(dirname "$0")/.."
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "   .env créé : à remplir"; }
mkdir -p user_data/logs user_data/data

echo
echo "OK. Déconnectez-vous / reconnectez-vous (groupe docker), puis suivez le README §5."
