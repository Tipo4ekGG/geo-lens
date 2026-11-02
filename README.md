# Geo Lens — быстрый ИИ и полный geo-sleuth

**Без аренды сервера: [установка на Intel Mac, Ventura 13+](server/macos/README.md).** Подготовлен запуск без Docker, с оригинальными Python-операторами и ограничением памяти. Совместимость и работа внешних сервисов проверяются установщиком и первым заданием.

Полный режим с Python, Chromium, OCR, обратным поиском, кандидатами и ML-операторами: [установка Oracle-сервера](server/README.md). Все исходные файлы geo-sleuth находятся в vendor/geo-sleuth. Полный режим требует подключённой VM и vision+tools API, не откатывается автоматически на быстрый анализ.

## GitHub Pages + Cloudflare Worker
Русский интерфейс исследования фото: загрузка, локальное чтение EXIF/GPS, ИИ-анализ через OpenAI-совместимый vision API, гипотезы места и JSON-отчёт.

## GitHub Pages
1. Создайте публичный репозиторий geo-lens и загрузите исходники.
2. Settings → Pages → Source: GitHub Actions.
3. Workflow Deploy GitHub Pages соберёт сайт на push в main. Ожидаемый адрес после успешного деплоя: https://tipo4ekgg.github.io/geo-lens/.

## API Worker
GitHub Pages не выполняет серверный код. API-ключ хранится в Cloudflare Worker.
1. npm ci && npm run build
2. Разверните dist/worker.js как Cloudflare Worker geo-lens-api (конфигурация wrangler.jsonc; можно использовать Wrangler CLI).
3. Добавьте секрет PHOTO_API_KEY — ключ провайдера, и отдельный секрет ACCESS_TOKEN — случайный длинный код доступа к обработке (рекомендуется 32 случайных байта). Настоящих ключей в этом репозитории нет.
4. Переменные Worker: PHOTO_API_ORIGIN — точный HTTPS origin API без пути; ALLOWED_ORIGIN — https://tipo4ekgg.github.io (без /geo-lens и завершающего слеша).
5. На сайте в «Подключение» укажите URL Worker, код доступа и путь API из документации (например /v1). Нажмите «Проверить и получить модели». Выберите vision-модель.

freecodex.fun указан как известный домен сервиса, а не подтверждённый endpoint. Если документация даёт другой домен, измените PHOTO_API_ORIGIN. Работоспособность реального API пока не проверена.

Код доступа хранится только в памяти вкладки. URL Worker, ID модели и путь — в localStorage. EXIF читается локально. Для ИИ передаётся JPEG-копия до 1600 px. Worker не сохраняет фото и отчёты. ИИ-ответ — гипотеза, не независимая проверка. В быстром режиме Python geo-sleuth, поиск изображений, панорамы и анализ рельефа не запускаются. В полном режиме используются операторы на отдельно подключённом сервере.

## Разработка
npm ci
npm run build
npm test

Сборка: public/ для GitHub Pages, dist/worker.js для Cloudflare. Тесты используют подставной API, не расходуют баланс провайдера. Это вариант для GitHub, независимый от приватной версии в Sites; ключ из Sites автоматически не переносится в ваш Cloudflare.
