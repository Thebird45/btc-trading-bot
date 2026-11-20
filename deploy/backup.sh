#!/usr/bin/env bash
# Copia de seguridad consistente de la base del paper trading (aunque el bot esté escribiendo).
# Guarda 14 días en data/backups/. Lo programa setup-vm.sh en cron.
set -euo pipefail
cd "$(dirname "$0")/.."

DB=data/paper.db
[[ -f "$DB" ]] || { echo "$(date -Is) sin base todavía"; exit 0; }

mkdir -p data/backups
OUT="data/backups/paper-$(date +%Y%m%d).db"
sqlite3 "$DB" ".backup '$OUT'"
find data/backups -name 'paper-*.db' -mtime +14 -delete
echo "$(date -Is) respaldo en $OUT"
