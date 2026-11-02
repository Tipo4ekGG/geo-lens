#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != x86_64 ]; then echo 'Этот установщик предназначен для Intel Mac.'; exit 1; fi
major=$(sw_vers -productVersion | cut -d. -f1)
if [ "$major" -lt 13 ]; then echo 'Подготовленная конфигурация требует macOS Ventura 13 или новее.'; exit 1; fi
if [ ! -x /usr/bin/sandbox-exec ]; then echo 'Нужен macOS sandbox-exec. Установка остановлена.'; exit 1; fi
state="$HOME/Library/Application Support/GeoLens"
cache="$HOME/Library/Caches/GeoLens"
mkdir -p "$state/bin" "$cache/browsers"
chmod 700 "$state"
export PATH="$state/bin:$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
 installer=$(mktemp)
 curl -fsSL https://astral.sh/uv/install.sh -o "$installer"
 UV_INSTALL_DIR="$state/bin" UV_NO_MODIFY_PATH=1 sh "$installer"
 rm -f "$installer"
fi
cd "$root"
uv python install 3.11
uv venv --python 3.11 .venv-api
uv venv --python 3.11 .venv-tools
uv pip install --python .venv-api/bin/python -r server/requirements.txt psutil==6.1.1
uv pip install --python .venv-tools/bin/python --no-deps -r server/macos/tools.lock
# Prefer Apple's local OCR; RapidOCR remains available if Vision cannot be installed.
if ! uv pip install --python .venv-tools/bin/python pyobjc-framework-Vision==10.3.2 pyobjc-framework-Quartz==10.3.2; then
 echo 'Apple Vision bridge недоступен; OCR будет использовать RapidOCR.'
fi
PLAYWRIGHT_BROWSERS_PATH="$cache/browsers" .venv-tools/bin/python -m playwright install chromium
chmod +x server/macos/uv-native
if [ ! -x "$state/bin/cloudflared" ]; then
 tmp=$(mktemp -d)
 curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz -o "$tmp/cloudflared.tgz"
 tar -xzf "$tmp/cloudflared.tgz" -C "$tmp"
 install -m 755 "$tmp/cloudflared" "$state/bin/cloudflared"
 rm -rf "$tmp"
fi
.venv-api/bin/python -m server.macos.check
.venv-api/bin/python -m server.macos.configure
printf '\nУстановка завершена. Для запуска откройте Start Geo Lens.command.\n'
