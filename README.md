# Квитто — API платежей

Сервис, через который онлайн-школа принимает оплату курса: тарифы, создание платежа (промокод,
рассрочка, идемпотентность), просмотр платежа и уведомления банка о смене статуса.

**Стек:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, PostgreSQL 16,
Alembic, uv, pytest, Docker Compose.

## Быстрый старт

Нужен только Docker.

```bash
docker compose up --build
```

При старте контейнер применяет миграции (они же создают тарифы) и поднимает API на
`http://localhost:8000`. Документация OpenAPI — `http://localhost:8000/docs`,
схема — `http://localhost:8000/openapi.json`.

> Порт `5432` занят локальным Postgres? Остановите его или поменяйте проброс порта `db`
> в `docker-compose.yml`.

## Тесты

Тесты работают с настоящим Postgres: с отдельной базой `kvitto_test`, которую создаёт
`docker/postgres/init.sql` при первом запуске контейнера. Нужен [uv](https://docs.astral.sh/uv/).

```bash
docker compose up -d db
uv sync
uv run pytest
```

> Ошибка `database "kvitto_test" does not exist`? Docker-том Postgres был создан раньше, чем
> появился `init.sql`, а скрипты инициализации выполняются только на пустом томе. Пересоздайте
> том: `docker compose down -v && docker compose up -d db`. Команда удаляет локальные данные.

Линтеры и типы:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy .
```

## CI

GitHub Actions ([.github/workflows/ci.yml](.github/workflows/ci.yml)) запускается на каждый push
и pull request. В нём три джобы:
- **Lint and types** — `ruff check`, `ruff format --check`, `mypy --strict`;
- **Tests** — `pytest` против Postgres из service-контейнера;
- **Docker Compose smoke test** — `docker compose up --build --wait`, затем запросы к `/health`
  и `/tariffs`. Так проверяется, что проект поднимается по инструкции из README и миграции
  создают тарифы.

## Локальная разработка без контейнера приложения

```bash
docker compose up -d db
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Примеры запросов

Все суммы — целые числа в **копейках**: 19 900 ₽ → `1990000`.

### Тарифы
```bash
curl -s localhost:8000/tariffs
```
```json
[{"id":"basic","title":"Basic","price":990000},
 {"id":"standard","title":"Standard","price":1990000},
 {"id":"premium","title":"Premium","price":2990000}]
```

### Создать платёж картой
```bash
curl -s -X POST localhost:8000/payments \
  -H 'Content-Type: application/json' \
  -d '{"tariff_id": "basic", "email": "user@example.com", "method": "card"}'
```
Ответ `201`, платёж в статусе `pending`, `schedule: null`.

### Рассрочка с промокодом и ключом идемпотентности
```bash
curl -s -X POST localhost:8000/payments \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: order-1001' \
  -d '{"tariff_id": "standard", "email": "user@example.com", "method": "installment",
       "installment_months": 3, "promo_code": "kvitto10"}'
```
```json
{"id":"…","status":"pending","tariff_id":"standard","amount":1791000,"discount":199000,
 "method":"installment","installment_months":3,"schedule":[597000,597000,597000],
 "email":"user@example.com","created_at":"…"}
```
- Повтор **того же** запроса с тем же ключом вернёт тот же платёж с кодом `200`, второй не создастся.
- Тот же ключ с **другим** телом — `422` с `type: "idempotency_key_reused"`.

### Получить платёж
```bash
curl -s localhost:8000/payments/<payment_id>
```
Нет такого платежа — `404 {"detail": "Payment not found"}`.

### Список платежей с фильтрами
```bash
curl -s 'localhost:8000/payments?email=user@example.com&status=pending&limit=10&offset=0'
```
Новые сверху. Все параметры необязательны: `email` (без учёта регистра), `status`,
`limit` от 1 до 100 (по умолчанию 50), `offset`.

### Уведомление банка
Запрос подписывается: `X-Signature` — hex HMAC-SHA256 от **сырого тела** с секретом
`WEBHOOK_SECRET`. В `docker compose` по умолчанию это `dev-webhook-secret`.
```bash
BODY='{"payment_id": "<payment_id>", "status": "succeeded"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac 'dev-webhook-secret' | awk '{print $NF}')
curl -s -X POST localhost:8000/webhooks/bank \
  -H 'Content-Type: application/json' \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```
- Нет подписи или она неверная — `401 {"detail": "Invalid signature"}`.
- Успех — `200 {"result": "ok"}`.
- Запрещённый переход (например, `succeeded → failed`) — `409 {"error": "invalid_transition"}`, статус не меняется.
- Нет такого платежа — `404`.

## Правила

| Что | Правило |
|---|---|
| Промокод | `KVITTO10` — −10% от цены тарифа; регистр и пробелы по краям не важны; неизвестный код → `422` |
| Скидка | округляется вниз до копейки (целочисленная арифметика, без `float`) |
| Способ оплаты | `card`, `sbp`, `installment`; для `installment` обязателен `installment_months` ∈ {3, 6, 12}, для остальных он запрещён |
| График | сумма делится на срок; лишние копейки — в первые платежи; сумма графика ровно равна `amount` |
| Статусы | `pending → succeeded`, `pending → failed`, `succeeded → refunded`; остальное — `409` |

Ошибки валидации — стандартный ответ FastAPI `422`. Бизнесовые `422` (тариф, промокод, ключ
идемпотентности) отдаются в том же формате.

## Как устроено

```
app/api/       HTTP: роутеры, маппинг доменных ошибок в коды ответов
app/services/  сценарии: транзакции и запросы к БД
app/domain/    чистые правила: деньги, промокод, переходы статусов
app/db/        модели SQLAlchemy и сессия
migrations/    Alembic: схема и сид тарифов
tests/         unit (domain), db (схема и ограничения), api, services (гонки)
```

- Инварианты денег продублированы `CHECK`-ограничениями в БД.
- Повторы с одним ключом защищены уникальным индексом и `INSERT ... ON CONFLICT`.
- Параллельные вебхуки сериализуются через `SELECT ... FOR UPDATE`. Обе гонки покрыты тестами
  на реальных параллельных транзакциях.

Подробности:
- [docs/SPEC.md](docs/SPEC.md) — спецификация;
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура;
- [docs/DECISIONS.md](docs/DECISIONS.md) — принятые решения и компромиссы, включая места,
  где ТЗ допускает разные трактовки.

Работа с ИИ-ассистентом описана в [AI_LOG.md](AI_LOG.md), правила для агентов —
в [CLAUDE.md](CLAUDE.md).
