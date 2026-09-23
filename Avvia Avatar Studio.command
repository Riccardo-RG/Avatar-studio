#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if /usr/bin/curl --connect-timeout 2 --max-time 3 -fsS http://127.0.0.1:8765/api/bootstrap >/dev/null 2>&1; then
  /usr/bin/open http://127.0.0.1:8765
  exit 0
fi
studio_python="$PWD/.venv/bin/python"
if [ ! -x "$studio_python" ]; then
  echo 'Ambiente locale non preparato. Esegui prima Prepara Mac.command.'
  read -r '?Premi Invio per chiudere.'
  exit 1
fi
if ! "$studio_python" -c 'import platform,sys; import piper,imageio_ffmpeg; raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,14)))' >/dev/null 2>&1; then
  echo 'Dipendenze o Python non compatibili. Esegui Prepara Mac.command per riparare questo ambiente.'
  read -r '?Premi Invio per chiudere.'
  exit 1
fi
"$studio_python" app.py &
studio_pid=$!
trap 'kill "$studio_pid" 2>/dev/null' EXIT INT TERM
for attempt in {1..30}; do
  if ! kill -0 "$studio_pid" 2>/dev/null; then break; fi
  if /usr/bin/curl --connect-timeout 2 --max-time 3 -fsS http://127.0.0.1:8765/api/bootstrap >/dev/null 2>&1; then
    /usr/bin/open http://127.0.0.1:8765
    echo 'Avatar Studio è aperto. Lascia questa finestra aperta mentre produci i video.'
    echo 'Per chiudere lo studio premi Ctrl+C.'
    wait "$studio_pid"
    exit $?
  fi
  sleep 1
done
echo 'Avvio non riuscito. Controlla il messaggio di errore qui sopra.'
read -r '?Premi Invio per chiudere.'
exit 1
