#!/usr/bin/env bash
# Sauvegarde quotidienne : base PostgreSQL + factures importées. Garde 14 jours.
# À lancer depuis le dossier du projet sur le serveur (voir DEPLOIEMENT.md pour la planification).
set -euo pipefail
cd "$(dirname "$0")/.."
C="docker compose -f docker-compose.prod.yml --env-file .env"
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p backups
$C exec -T db pg_dump -U tva tva | gzip > "backups/base-$STAMP.sql.gz"
$C exec -T app tar -C /data -czf - uploads > "backups/factures-$STAMP.tar.gz"
# un fichier vide = sauvegarde ratée
for f in "backups/base-$STAMP.sql.gz" "backups/factures-$STAMP.tar.gz"; do
  [ -s "$f" ] || { echo "ERREUR : $f est vide" >&2; exit 1; }
done
find backups -type f \( -name 'base-*.sql.gz' -o -name 'factures-*.tar.gz' \) -mtime +14 -delete
echo "$(date '+%F %T') sauvegarde OK : base-$STAMP.sql.gz, factures-$STAMP.tar.gz"
