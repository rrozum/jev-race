# Decision Lab на VPS

Площадка https://decision.rrozum.pro/ включает главную страницу с картой проектов, Race по /race/ и Vision по /vision/. Старый https://jev-race.rrozum.pro/ отвечает постоянным 308 на /race/ нового домена, сохраняя путь и параметры запроса.

## Структура сервера

Ubuntu 24.04, 1 vCPU, 1 GB RAM. Каталоги проектов расположены рядом:

```text
/opt/jev-race/        # race, Web-экспорт Godot, конфигурация площадки
/opt/jev-vision/      # отдельное приложение vision и закрытый .env
```

A-запись decision.rrozum.pro указывает на IP VPS. Caddy занимает 80/443 и сам выпускает сертификаты. Контейнеры приложений доступны только внутри Docker. Главная — статические файлы из portal/, без отдельного runtime.

## Подготовка

1. Соберите Web-экспорт race в web/game согласно основному README.
2. Разместите jev-vision рядом с jev-race и заполните его .env по .env.example. Ключ TypeSafe используется только сервером vision; race продолжает принимать токен посетителя.
3. Настройте A-запись decision.rrozum.pro и сохраните старый домен для редиректа. Откройте TCP 80 и 443.
4. Установите Docker Engine и Compose plugin.

Из корня jev-race:

```bash
docker compose -f deploy/vps/compose.yaml build race vision
docker compose -f deploy/vps/compose.yaml run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
docker compose -f deploy/vps/compose.yaml up -d --wait
curl -fsS https://decision.rrozum.pro/race/healthz
curl -fsS https://decision.rrozum.pro/vision/healthz
```

Caddy снимает префиксы /race и /vision перед передачей запросов приложениям. Пути HTML/JS/CSS относительно страницы, поэтому ресурсы, API и игровой iframe остаются внутри подпроекта. Канонические адреса заканчиваются слешем; /race и /vision перенаправляются на них.

## Данные и обновление

Не удаляйте volumes: vps_caddy_data хранит сертификаты, vps_vision_budget — дневной счетчик оплачиваемых попыток vision. Фотографий и токенов в этих томах нет. Секрет находится только в закрытом /opt/jev-vision/.env и окружении процесса vision. Не публикуйте docker compose config без редактирования секретов.

Для обновления повторите build и up --wait. При изменении Caddyfile проверьте конфигурацию и выполните:

```bash
docker compose -f deploy/vps/compose.yaml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Логи ограничены 3 файлами по 10 MB на контейнер; приложения не пишут access logs или тела запросов. У vision 256 MB RAM, у race 512 MB. Общий оплачиваемый ключ vision ограничен 1000 попытками в сутки UTC, двумя одновременными запросами и одним запросом в секунду на IP. Проверка Origin не является авторизацией.

## Откат миграции 17 октября 2026

До переключения сохранены конфигурация /opt/decision-backup-20261017/deploy и образ jev-race:before-decision-20261017. Сертификаты и другие volumes сохранены. Чтобы вернуть старую схему, восстановите compose.yaml/Caddyfile из этой копии, укажите image jev-race:before-decision-20261017 без пересборки и выполните compose up -d --no-build. Проверьте старый HTTPS-адрес. Новый контейнер vision можно остановить отдельно; его том не удаляйте. DNS-запись decision удалять для отката приложения не требуется.
