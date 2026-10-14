# Деплой на хостинг (задача 9.6)

Стенд из пяти контейнеров на одном VPS (достаточно 2 vCPU / 2 ГБ RAM / 60 ГБ SSD, Ubuntu 24.04). Образы собираются на GitHub
(`.github/workflows/publish.yml`) и лежат в `ghcr.io/alexandrag-code/veildeck-*`; сервер ничего не собирает и **не обращается
к Docker Hub** (из РФ он недоступен без VPN).

Ограничения проекта (`AGENTS.md` §2): доступ закрытый (basic auth), только синтетические данные, сканеры и ZAP не гонять
по хосту без проверки правил хостинга, секреты создаются на сервере и в git не попадают.

## 0. Что должно быть готово

- В `main` прошёл зелёный CI, затем выполнился workflow **Publish images** (вкладка Actions): в Packages репозитория
  появились `veildeck-api`, `veildeck-web`, `veildeck-postgres`, `veildeck-redis`, `veildeck-mailpit`.
- Известен IP сервера (домена пока нет; когда появится, см. раздел «Домен» внизу).

## 1. Первичная настройка сервера (один раз, под root)

```bash
# Пользователь для работы и вход только по ключу
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/ && chown -R deploy:deploy /home/deploy/.ssh
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh   # перед этим в другом окне проверьте вход под deploy!

# Файрвол: наружу только SSH, HTTP и HTTPS
apt update && apt install -y ufw fail2ban make git openssl docker.io docker-compose-v2
ufw default deny incoming && ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
usermod -aG docker deploy

# Swap 2 ГБ: на 2 ГБ RAM пик (рендер PDF, перезапуск) без него убивает контейнеры
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Дальше всё под пользователем `deploy`.

## 2. Репозиторий, секреты, сертификат, пароль

```bash
git clone https://github.com/AlexandraG-code/VeilDeck.git && cd VeilDeck
make secrets                     # .env со случайными ключами; создаётся ТОЛЬКО на сервере
make certs-ip IP=<IP_СЕРВЕРА>    # самоподписанный сертификат (браузер предупредит; пока нет домена)
make basic-auth NAME=demo        # логин и пароль закрытого доступа (deploy/htpasswd)
```

## 3. Вход в реестр и первый запуск

Пакеты в ghcr приватные, поэтому нужен токен. В GitHub: Settings → Developer settings → Personal access tokens
(classic) → scope **`read:packages`**. Токен хранится только на сервере.

```bash
echo '<ТОКЕН>' | docker login ghcr.io -u AlexandraG-code --password-stdin
make deploy                      # docker compose pull && up -d (файл deploy/docker-compose.prod.yml)
docker compose -f deploy/docker-compose.prod.yml --env-file .env ps
```

Проверка с вашего компьютера: `curl -k https://<IP>/healthz` → `{"status":"ok"}`; в браузере `https://<IP>/` запросит
логин и пароль (basic auth), предупреждение сертификата принять.

`make deploy` сам передаёт ключ сертификата и `htpasswd` пользователю uid 101 (под ним работает nginx), для этого нужен `sudo`.
Без этого nginx падает с `Permission denied` на `localhost-key.pem`.

Обновление после нового коммита в `main` (когда Publish images снова отработал): `make deploy`.

## 4. Если ghcr.io недоступен с сервера

Любой реестр обходится передачей образа по SSH. С вашего компьютера (или из Actions-артефакта):

```bash
for i in api web postgres redis mailpit; do
  docker pull --platform linux/amd64 ghcr.io/alexandrag-code/veildeck-$i:latest
done
docker save $(docker images --format '{{.Repository}}:{{.Tag}}' | grep veildeck- ) | ssh deploy@<IP> docker load
```

Затем на сервере тот же `make deploy`, но без шага `pull` (`docker compose … up -d`). Теги `postgres:16-alpine`,
`redis:7-alpine`, `mailpit:v1.31.4` фиксированы в `docker-compose.prod.yml`.

## 5. Mailpit и база: как смотреть

Порты Mailpit и PostgreSQL наружу не публикуются. Письма: `ssh -L 8025:127.0.0.1:8025 deploy@<IP>`, затем
http://localhost:8025. Внутри Docker-сети сервисы видят друг друга по именам.

## 6. Домен (когда появится)

Пока сертификат самоподписанный. С доменом: направить A-запись на IP, выпустить сертификат Let's Encrypt
(`certbot certonly --standalone -d <домен>` при остановленном nginx, порт 80) и положить `fullchain.pem` и `privkey.pem`
в `deploy/certs/localhost.pem` и `localhost-key.pem` (имена те же, конфиг менять не нужно); обновление — по cron/systemd timer
с перезапуском nginx. Cookie `__Host-` работают только по HTTPS с валидным сертификатом.

## 7. Что проверено, а что нет

Проверено локально: синтаксис и поведение `deploy/nginx/prod.conf` (401 без пароля, 200 с паролем, `/healthz` открыт,
редирект 80→443), валидность `docker-compose.prod.yml`, цели `make certs-ip`, `basic-auth`, `deploy`.
**Не проверено на реальном сервере:** шаги раздела 1 и 3 (Docker из `apt`, доступность `ghcr.io`, workflow Publish images
на GitHub: он ещё ни разу не запускался). Первый прогон может потребовать правок.

## 8. Известные ограничения

Одиночный сервер без резервного копирования и мониторинга (остаточный риск №6, `design.md` §10).
Роль БД `app_rw` и первые миграции создаёт сервис `db-init` до запуска API.
Описание доступного среза и ограничений — [database-rest.md](../docs/database-rest.md).
