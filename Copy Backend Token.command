#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv-api/bin/python ]; then echo 'Сначала установите приложение.'; exit 1; fi
set -o pipefail
.venv-api/bin/python -c 'import json,sys; from pathlib import Path; sys.stdout.write(json.loads((Path.home()/"Library/Application Support/GeoLens/config.json").read_text())["backend_token"])' | /usr/bin/pbcopy
if [ "$?" -eq 0 ]; then echo 'Код сервера скопирован. Вставьте его только в Secret FULL_BACKEND_TOKEN в Cloudflare.'; fi
read -rp 'Нажмите Enter…' _
