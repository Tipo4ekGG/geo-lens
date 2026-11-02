#!/bin/bash
cd "$(dirname "$0")"
if [ ! -x .venv-api/bin/python ]; then echo 'Сначала запустите Install on Intel Mac.command'; read -rp 'Enter…' _; exit 1; fi
.venv-api/bin/python -m server.macos.launch
