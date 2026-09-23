#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
studio_python=""
studio_native_arm="$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null)"
for candidate in /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3; do
  if [ -x "$candidate" ] && "$candidate" -c 'import sys,tarfile,platform; raise SystemExit(not ((3,11) <= sys.version_info[:2] < (3,14) and hasattr(tarfile,"data_filter") and (sys.argv[1] != "1" or platform.machine() == "arm64")))' "$studio_native_arm" >/dev/null 2>&1; then studio_python="$candidate"; break; fi
done
if [ -z "$studio_python" ]; then studio_python="$(command -v python3)"; fi
if [ -z "$studio_python" ]; then
  echo 'Installa Python 3.11–3.13 per macOS da https://www.python.org/downloads/macos/ e riprova.'
  studio_result=1
else
  "$studio_python" setup_mac.py
  studio_result=$?
  if [ "$studio_result" -ne 0 ]; then echo 'Preparazione interrotta. Correggi il problema indicato e riapri questo file: i download dei modelli possono riprendere.'; fi
fi
read -r '?Premi Invio per chiudere.'
exit "$studio_result"
