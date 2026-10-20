#!/usr/bin/env bash
# Préparation d'un serveur Ubuntu (Oracle Cloud) : Docker + ouverture des ports 80 et 443.
# À lancer UNE fois : bash scripts/setup_vm.sh
set -euo pipefail
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git curl ca-certificates iptables-persistent
# Docker (script officiel)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
# Les images Ubuntu d'Oracle bloquent tout par défaut avec iptables : on ouvre le web (avant la règle REJECT)
N=$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')
N=${N:-1}
sudo iptables -I INPUT "$N" -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT "$N" -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save
echo "Terminé. Déconnectez-vous puis reconnectez-vous en SSH pour que le groupe docker soit pris en compte."
