#!/usr/bin/env bash
# Installe la pile ANSUT sur un Ubuntu neuf : Docker, Odoo 17, les modules.
# Usage : bash installer-vps.sh
set -euo pipefail

BASE=${BASE:-ansut}
DEPOT=${DEPOT:-$HOME/absut-stock}

echo "== 1/5 Docker =="
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl git
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
fi
docker --version

echo "== 2/5 Les modules =="
if [ -d "$DEPOT/.git" ]; then
  git -C "$DEPOT" pull --ff-only
else
  git clone https://github.com/SOMET1010/ABSUT-STOCK.git "$DEPOT"
fi
cd "$DEPOT"

echo "== 3/5 Démarrage de la pile =="
# sudo : l'appartenance au groupe docker ne prend effet qu'à la reconnexion.
sudo docker compose up -d
echo "   attente de PostgreSQL…"
until sudo docker compose exec -T db pg_isready -U odoo -d postgres >/dev/null 2>&1; do sleep 2; done

echo "== 4/5 Installation des modules dans la base « $BASE » =="
sudo docker compose run --rm odoo odoo -d "$BASE" \
  -i ansut_stock,ansut_demo --stop-after-init

echo "== 5/5 Redémarrage =="
sudo docker compose restart odoo

IP=$(curl -s -m 5 ifconfig.me || echo "IP_DU_VPS")
cat <<FIN

  ✅ Terminé.

  Depuis votre PC Windows, ouvrez un tunnel puis http://localhost:8069 :

      ssh -L 8069:localhost:8069 $USER@$IP

  Identifiants : admin / admin
  Application ANSUT → Point de retrait → PIN de démonstration : 123456

  Journaux :   cd $DEPOT && sudo docker compose logs -f odoo
  Arrêter :    cd $DEPOT && sudo docker compose down

FIN
