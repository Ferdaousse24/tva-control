#!/usr/bin/env bash
# Sauvegarde : base PostgreSQL + fichiers importés. À lancer depuis le dossier du projet.
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p backups
docker compose exec -T db pg_dump -U tva tva | gzip > "backups/base-$STAMP.sql.gz"
docker compose cp app:/data/uploads "backups/uploads-$STAMP" >/dev/null
tar -czf "backups/uploads-$STAMP.tar.gz" -C backups "uploads-$STAMP" && rm -rf "backups/uploads-$STAMP"
echo "Sauvegarde créée dans backups/ (copiez-la sur un autre support : Drive, disque externe)."
