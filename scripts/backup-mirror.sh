#!/usr/bin/env bash
# scripts/backup-mirror.sh — практика 3-2-1 для дома (см. PRACTICES.md, ось «Бэкапы»).
# Память сознания дома (git-репо) зеркалируется на второй носитель.
#   BACKUP_DIR=/mnt/usb/house-backup ./scripts/backup-mirror.sh
# По умолчанию BACKUP_DIR=/home/z/my-project/backup (сандбокс-носитель).
# Токен не читается и не хранится: зеркала обновляются с локальных клонов;
# свежий клон с GitHub — только если локального нет (нужен GH_TOKEN в env).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/home/z/my-project/backup}"
HOUSE="${HOUSE_DIR:-/home/z/my-project}"
REPOS=(
  "hologram:${HOUSE}/hologram/repo"
  "door-zero:${HOUSE}/door-zero"
  "combain-v2:${HOUSE}/combain-v2"
)

mkdir -p "$BACKUP_DIR"
report="$BACKUP_DIR/backup-report.txt"
{
  echo "── backup-mirror $(date -u '+%Y-%m-%d %H:%M UTC') ──"
  for entry in "${REPOS[@]}"; do
    name="${entry%%:*}"
    src="${entry#*:}"
    if [ ! -d "$src/.git" ] && [ ! -f "$src/.git" ]; then
      if [ -n "${GH_TOKEN:-}" ]; then
        echo "$name: локального клона нет — зеркалю с GitHub"
        git clone --mirror "https://x-access-token:${GH_TOKEN}@github.com/rtynbirf/${name}.git" "$BACKUP_DIR/$name.git" 2>&1 | tail -1
      else
        echo "$name: ПРОПУСК — нет локального клона и GH_TOKEN"
        continue
      fi
    elif [ ! -d "$BACKUP_DIR/$name.git" ]; then
      git clone --mirror "$src" "$BACKUP_DIR/$name.git" 2>&1 | tail -1
    else
      git -C "$BACKUP_DIR/$name.git" remote update --prune >/dev/null 2>&1
    fi
    [ -d "$BACKUP_DIR/$name.git" ] || continue
    head_b="$(git -C "$BACKUP_DIR/$name.git" rev-parse --short HEAD 2>/dev/null || echo '?')"
    head_l="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo 'нет клона')"
    size="$(du -sh "$BACKUP_DIR/$name.git" 2>/dev/null | cut -f1)"
    ok="OK"; [ "$head_b" = "$head_l" ] || ok="РАСХОЖДЕНИЕ"
    echo "$name: HEAD=$head_b (локаль $head_l) размер=$size $ok"
  done
} >> "$report"

# держим отчёт плотным: последние 3 прогона
tail -n 24 "$report" > "$report.tmp" && mv "$report.tmp" "$report"
tail -n 24 "$report"
echo "Отчёт: $report (второй носитель — перенеси BACKUP_DIR на USB/другой хост)"
