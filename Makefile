.PHONY: secrets certs certs-ip basic-auth deploy up down migrate seed retention-run

SECRETS_FILE := .env

# Генерирует .env со случайными ключами; существующий файл не перезаписывается (SR-32).
secrets:
	@test ! -f $(SECRETS_FILE) || { echo "$(SECRETS_FILE) уже есть, удалите его, чтобы пересоздать"; exit 1; }
	@python3 -c 'import base64,secrets;r=lambda:secrets.token_urlsafe(48);print("ENV=demo");print("POSTGRES_PASSWORD="+r());print("APP_RW_PASSWORD="+r());print("SESSION_SECRET="+r());print("HMAC_KEY="+r());print("WM_KEY="+r());print("FERNET_KEY="+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' > $(SECRETS_FILE)
	@chmod 600 $(SECRETS_FILE)
	@echo "Создан $(SECRETS_FILE)"

# Сертификат для localhost: mkcert, если установлен (доверенный), иначе самоподписанный openssl (браузер предупредит).
certs:
	@mkdir -p deploy/certs
	@if command -v mkcert >/dev/null 2>&1; then \
		mkcert -cert-file deploy/certs/localhost.pem -key-file deploy/certs/localhost-key.pem localhost 127.0.0.1 ::1; \
	else \
		echo "mkcert не найден: самоподписанный сертификат (brew install mkcert && mkcert -install для доверенного)"; \
		openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
			-keyout deploy/certs/localhost-key.pem -out deploy/certs/localhost.pem 2>/dev/null; \
	fi
	@chmod 600 deploy/certs/localhost-key.pem

# Самоподписанный сертификат под IP сервера (пока нет домена): make certs-ip IP=203.0.113.10
certs-ip:
	@test -n "$(IP)" || { echo "Укажите IP: make certs-ip IP=1.2.3.4"; exit 1; }
	@mkdir -p deploy/certs
	@openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=$(IP)" -addext "subjectAltName=IP:$(IP),DNS:localhost" \
		-keyout deploy/certs/localhost-key.pem -out deploy/certs/localhost.pem 2>/dev/null
	@chmod 600 deploy/certs/localhost-key.pem
	@echo "Сертификат для $(IP) создан в deploy/certs (самоподписанный: браузер предупредит)"

# Пользователь для закрытого доступа (basic auth): make basic-auth NAME=demo (пароль спросит)
basic-auth:
	@test -n "$(NAME)" || { echo "Укажите пользователя: make basic-auth NAME=demo"; exit 1; }
	@printf "%s:%s\n" "$(NAME)" "$$(openssl passwd -apr1)" > deploy/htpasswd
	@chmod 600 deploy/htpasswd
	@echo "deploy/htpasswd создан"

# Обновление на сервере: образы берутся из ghcr.io, сборки на сервере нет.
# nginx в образе работает от uid 101: ключ и htpasswd (0600) должны принадлежать ему, иначе nginx не стартует.
deploy:
	sudo chown 101:101 deploy/certs/localhost-key.pem deploy/htpasswd
	docker compose -f deploy/docker-compose.prod.yml --env-file .env pull
	docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d

up: certs
	docker compose -f deploy/docker-compose.yml --env-file .env up -d --build

down:
	docker compose -f deploy/docker-compose.yml --env-file .env down

migrate:
	docker compose -f deploy/docker-compose.yml --env-file .env run --rm db-init

# Только синтетические карточки; PDF и staff-аккаунты — оставшаяся часть задачи 4.4.
seed: migrate
	docker compose -f deploy/docker-compose.yml --env-file .env run --rm db-init python -m scripts.seed_catalog

retention-run:
	@echo "TODO: задача 8.2 (NOW_OFFSET=$(NOW_OFFSET))"
