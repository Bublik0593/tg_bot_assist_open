#!/usr/bin/env bash
# Ежедневный бэкап SQLite через .backup (безопасно при работающем боте). Хранит 14 копий.
set -euo pipefail
DB="${DB_PATH:-/opt/bot_habits/data/bot.sqlite}"
OUT="${BACKUP_DIR:-/opt/bot_habits/backups}"
mkdir -p "$OUT"
sqlite3 "$DB" ".backup '$OUT/bot-$(date +%F).sqlite'"
ls -1t "$OUT"/bot-*.sqlite | tail -n +15 | xargs -r rm --
