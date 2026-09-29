# Публикация Race на VPS

Эта конфигурация запускает Race за Caddy с HTTPS для `jev-race.rrozum.pro`.
Пользователь вводит свой токен Jev в браузере. Токен не записывается в Compose,
Docker-образ или файлы сервера.

## Подготовка

1. Соберите Web-экспорт игры в `web/game` по инструкции основного README.
2. Направьте A-запись `jev-race.rrozum.pro` на публичный IP сервера.
3. Откройте входящие TCP-порты 80 и 443. Порт 80 нужен Caddy для выпуска
   и продления сертификата.
4. Установите Docker Engine и Compose plugin.

Запуск из корня репозитория:

```bash
docker compose -f deploy/vps/compose.yaml up -d --build
docker compose -f deploy/vps/compose.yaml ps
curl -fsS https://jev-race.rrozum.pro/healthz
```

Приложение слушает порт 8080 только внутри сети Docker. Caddy хранит сертификат
в Docker volume `vps_caddy_data`. При обновлении кода или Web-экспорта снова
выполните `docker compose -f deploy/vps/compose.yaml up -d --build`.

Логи обоих контейнеров ограничены тремя файлами по 10 МБ. Проверьте свободное
место и состояние контейнеров перед обновлением: `df -h /` и
`docker compose -f deploy/vps/compose.yaml ps`.
