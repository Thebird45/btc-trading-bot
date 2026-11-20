#!/usr/bin/env bash
# Trae la última versión de main, reconstruye la imagen y reinicia los servicios.
# Uso, dentro de la VM:  bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Falta .env. Copia .env.example a .env y complétalo (ver docs/despliegue.md)." >&2
  exit 1
fi
for var in DOMAIN WEB_PASSWORD_HASH WEB_SESSION_SECRET; do
  if ! grep -qE "^${var}=.+" .env; then
    echo "Falta ${var} en .env" >&2
    exit 1
  fi
done

mkdir -p data
# El contenedor corre con uid 1000: debe poder escribir en data/
sudo chown -R 1000:1000 data

git pull --ff-only
docker compose build --pull
docker compose up -d --remove-orphans
docker image prune -f >/dev/null

echo
docker compose ps
echo
echo "Logs del bot:  docker compose logs -f bot"
