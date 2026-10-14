# PostgreSQL и REST-каталог

Реализован срез задач 1.6/1.7, 2.1/2.4, 4.4 и 5.1: две таблицы PostgreSQL,
миграции Alembic, публичный REST-каталог и синтетические данные. Полные задачи MVP этим не закрываются.

| Объект БД | Назначение |
|---|---|
| `cards` | Полная карточка: teaser и confidential-поля; статусы draft/published/archived |
| `audit_events` | Неизменяемые события ограничения запросов, hash-цепочка |
| `catalog_cards` (view) | Только опубликованные карточки и девять разрешённых teaser-полей |

Миграции и seed выполняются под `app_owner`. API работает под `app_rw`: только SELECT
публичного представления, INSERT/SELECT аудита и использование его sequence. Прямого доступа
к закрытым полям `cards` у этой роли нет. Пароль owner не передаётся контейнеру API.
Данные PostgreSQL сохраняются в существующем volume `pgdata`.

## Запуск с Docker

Нужны Docker Compose v2, Python 3, make и openssl; mkcert необязателен.
В корне репозитория:

```bash
make secrets    # один раз, если .env ещё отсутствует
make up        # PostgreSQL → db-init (роль + Alembic) → API
make seed      # 12 published, один draft и один archived; повтор без дублей
curl -k 'https://localhost:8443/api/v1/cards?page=1&page_size=5'
```

Только синтетические данные. Каталог seed не создаёт PDF, аккаунты staff или доступы:
это оставшаяся часть 4.4. Повторный seed не перезаписывает существующие карточки.
`make down` сохраняет volume; `docker compose down -v` уничтожает данные.

Для обновления только схемы: `make migrate`. SQL-откат удаляет данные соответствующих таблиц:
из `backend/` — `alembic downgrade base`, затем `alembic upgrade head`;
требуется `MIGRATION_DATABASE_URL` с ролью `app_owner`.
На стенде из готовых образов команда `db-init` также запускается до API.
После `make deploy` заполнение: `docker compose -f deploy/docker-compose.prod.yml --env-file .env run --rm db-init python -m scripts.seed_catalog`.

## REST

| Метод | URL | Результат |
|---|---|---|
| GET | `/api/v1/cards` | `{items, page, page_size, total}` |
| GET | `/api/v1/cards/{UUIDv4}` | Одна опубликованная teaser-карточка |

Параметры списка: `page` от 1 до 100000, `page_size` от 1 до 20;
фильтры `industry`, `region_macro`, `deal_type` — только enum.
Полный контракт и значения enum: `docs/api/openapi.json`; клиент TypeScript сгенерирован orval.
При `ENV=demo` Swagger выключен по требованиям кейса.

```bash
curl -k 'https://localhost:8443/api/v1/cards?industry=manufacturing&region_macro=asia&deal_type=equity'
curl -k 'https://localhost:8443/api/v1/cards/d39a2aed-6ae6-4f40-80a5-e0d60d0591e0'
curl -k -i 'https://localhost:8443/api/v1/cards?page_size=10000' # 422
curl -k -i 'https://localhost:8443/api/v1/cards/123'             # 404
```

Ответ не содержит `org_name`, `org_aliases`, `full_description` и сведений о материалах.
Для draft/archived/отсутствующего/неверного ID — один формат 404; request_id уникален.
Неизвестные параметры отклоняются с 422. Redis ограничивает список и карточку общим окном
60 запросов за минуту на peer-IP; затем 429 и `Retry-After`. IP хранится только в виде HMAC.
При сбое БД или Redis — безопасный 503. Отказ лимитера пишется в аудит не чаще раза в минуту
для одного IP, с advisory lock и SHA-256 цепочкой; UPDATE/DELETE/TRUNCATE запрещены.

Лимитер не доверяет присланным клиентом X-Forwarded-For/X-Real-IP. В существующей конфигурации
nginx приложение видит IP прокси, поэтому у посетителей через один прокси общее окно 60/мин.
До многопользовательского стенда требуется отдельная настройка доверенных прокси и передачи peer-IP.
Открытые POST/PATCH/DELETE не добавляются: по кейсу запись требует staff-сессии, CSRF и аудита.

## Тесты

Из `backend/`: `pytest -q`, `ruff check .`, `ruff format --check .`, `lint-imports`.
Без инфраструктуры тесты PostgreSQL/Redis явно пропускаются. Для сквозного прогона задайте:

- `TEST_DATABASE_OWNER_URL`: asyncpg URL отдельной БД, имя которой заканчивается на `_test`, роль app_owner;
- `TEST_APP_RW_PASSWORD`: тестовый пароль не короче 32 символов;
- `TEST_REDIS_URL`: отдельная Redis БД **15**, которую тесты очищают.

CI поднимает PostgreSQL 16 и Redis 7 и выполняет интеграционные тесты автоматически.
Не задавайте тестам адрес рабочей базы или общего Redis.
