#!/bin/bash
cd "$(dirname "$0")"
bash server/macos/install.sh
status=$?
echo
if [ "$status" -ne 0 ]; then echo 'Установка не завершена. Пришлите текст ошибки без ключа API.'; fi
read -rp 'Нажмите Enter, чтобы закрыть окно…' _
exit "$status"
