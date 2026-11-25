#!/bin/bash
# Перезапускает рендер при падении, пока все кадры не готовы.
PY="$1"; P="$2"
for i in $(seq 1 30); do
  "$PY" "$P/blender/render_all.py" "$P" 50 4 2>&1 | grep --line-buffered -E "FRAME|ALLDONE|rror" >> "$P/renders/log.txt"
  grep -q ALLDONE "$P/renders/log.txt" && exit 0
  echo "restart $i" >> "$P/renders/log.txt"
done
