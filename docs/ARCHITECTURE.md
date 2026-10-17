# Архитектура

## 1. Принципы
- **Простота важнее абстракций.** Слоёв и абстракций ровно столько, сколько нужно задаче:
  без репозиториев, generic-сервисов, DI-контейнеров, метаклассов.
- **Деньги — чистые функции.** Вся арифметика и правила статусов в `domain/` без I/O,
  покрываются юнит-тестами таблично.
- **Корректность обеспечивает БД.** Инварианты продублированы `CHECK`/`UNIQUE`/`FK`-constraint'ами;
  гонки решаются средствами Postgres, а не проверками в Python.

## 2. Слои

```
HTTP ──► api/ (роутеры, схемы, маппинг ошибок)
           │  вызывает
           ▼
         services/ (use-case'ы, транзакции, SQL-запросы через ORM)
           │  вызывает              │  читает/пишет
           ▼                        ▼
         domain/ (чистые функции)  db/ (модели, сессия)
```

| Слой | Можно | Нельзя |
|---|---|---|
| `api/` | принимать/валидировать запрос, вызывать сервис, сериализовать ответ, маппить доменные исключения в HTTP | бизнес-логика, SQL |
| `services/` | открыть/закоммитить транзакцию, читать/писать модели, вызывать domain | знать про `Request`, `HTTPException`, коды ответов |
| `domain/` | вычисления, правила, доменные исключения | импорт SQLAlchemy, FastAPI, любой I/O |
| `db/` | ORM-модели, engine, sessionmaker | бизнес-логика |

Зависимости направлены только вниз: `api → services → domain/db`. `domain` ни от чего не зависит.

## 3. Структура репозитория

```
kvitto/
├── app/
│   ├── main.py              # create_app(): роутеры, exception handlers, lifespan
│   ├── config.py            # Settings (pydantic-settings): DATABASE_URL, WEBHOOK_SECRET
│   ├── api/
│   │   ├── deps.py          # SessionDep, verify_signature (X-Signature)
│   │   ├── errors.py        # exception handlers: domain error → HTTP
│   │   ├── health.py
│   │   ├── tariffs.py
│   │   ├── payments.py
│   │   └── webhooks.py
│   ├── schemas/             # Pydantic v2: запросы и ответы API
│   │   ├── errors.py        # ErrorDetail для OpenAPI
│   │   ├── tariff.py
│   │   ├── payment.py
│   │   └── webhook.py
│   ├── services/
│   │   ├── tariffs.py
│   │   ├── payments.py      # create_payment (идемпотентность), get_payment, list_payments
│   │   └── webhooks.py      # apply_bank_status
│   ├── domain/
│   │   ├── enums.py         # PaymentStatus, PaymentMethod (StrEnum)
│   │   ├── money.py         # calc_discount, build_schedule
│   │   ├── promo.py         # PROMO_CODES, normalize_promo_code, promo_discount_percent
│   │   ├── status.py        # ALLOWED_TRANSITIONS, ensure_transition_allowed
│   │   └── errors.py        # DomainError и наследники
│   └── db/
│       ├── base.py          # DeclarativeBase, naming convention
│       ├── session.py       # engine, session_factory, get_session
│       └── models.py        # Tariff, Payment
├── migrations/              # Alembic (async env.py)
│   └── versions/
│       ├── 0001_initial_schema.py
│       └── 0002_seed_tariffs.py
├── tests/
│   ├── conftest.py          # миграции, сессия с откатом, AsyncClient
│   ├── helpers.py           # подпись вебхука, проверка 422, очистка тестовой БД
│   ├── unit/                # domain (money, promo, status) и config
│   ├── db/                  # схема: сид, CHECK/FK/UNIQUE, откат миграций
│   ├── api/                 # эндпоинты через httpx против Postgres
│   └── services/            # гонки на реальных параллельных транзакциях
├── docker/postgres/init.sql # создаёт БД kvitto_test
├── docs/                    # SPEC, ARCHITECTURE, DECISIONS
├── .github/workflows/ci.yml # lint, тесты, smoke через docker compose
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── pyproject.toml           # зависимости + конфиг ruff/mypy/pytest
├── uv.lock
├── .env.example
├── README.md
├── AI_LOG.md
└── CLAUDE.md
```

## 4. Модель данных

### `tariffs`
| колонка | тип | ограничения |
|---|---|---|
| `id` | `VARCHAR(32)` | PK |
| `title` | `VARCHAR(100)` | NOT NULL |
| `price` | `BIGINT` | NOT NULL, `CHECK (price > 0)` |

### `payments`
| колонка | тип | ограничения |
|---|---|---|
| `id` | `UUID` | PK, генерируется в приложении (`uuid4`) |
| `status` | `VARCHAR(16)` | NOT NULL, `CHECK IN (...)`, default `pending` |
| `tariff_id` | `VARCHAR(32)` | NOT NULL, FK → `tariffs.id` |
| `email` | `VARCHAR(320)` | NOT NULL, индекс |
| `method` | `VARCHAR(16)` | NOT NULL, `CHECK IN ('card','sbp','installment')` |
| `installment_months` | `SMALLINT` | NULL, `CHECK IN (3,6,12)` |
| `price` | `BIGINT` | NOT NULL — снапшот цены тарифа |
| `discount` | `BIGINT` | NOT NULL, `CHECK (discount >= 0)` |
| `amount` | `BIGINT` | NOT NULL, `CHECK (amount > 0 AND amount = price - discount)` |
| `promo_code` | `VARCHAR(32)` | NULL, нормализованный (верхний регистр) |
| `schedule` | `BIGINT[]` | NULL |
| `idempotency_key` | `VARCHAR(255)` | NULL, `UNIQUE` |
| `request_hash` | `VARCHAR(64)` | NULL, sha256 канонического запроса |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |

Табличные CHECK:
- `(method = 'installment') = (installment_months IS NOT NULL)`
- `(method = 'installment') = (schedule IS NOT NULL)`
- `(idempotency_key IS NULL) = (request_hash IS NULL)`

Индексы: `email`, `status`, `created_at` (для бонуса 2).

Enum'ы — `VARCHAR + CHECK`, а не нативный `ENUM` Postgres: проще эволюционировать в миграциях.

## 5. Ключевые потоки

### 5.1 Создание платежа с идемпотентностью
```
POST /payments (body, Idempotency-Key?)
 1. Pydantic валидирует и нормализует body (email lower, promo upper/strip, правила installment)
 2. если ключ есть:
      request_hash = sha256(canonical_json(body))
      existing = SELECT ... WHERE idempotency_key = :key
      existing и hash совпал → 200 existing
      existing и hash другой → 422 idempotency_key_reused
 3. tariff = SELECT tariff (нет → 422 unknown_tariff)
 4. discount = calc_discount(tariff.price, resolve_promo(code))   # 422 unknown_promo_code
    amount   = price - discount
    schedule = build_schedule(amount, months) если installment
 5. INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING *
      строка вернулась → COMMIT → 201
      пусто (параллельный запрос успел первым) → SELECT по ключу → шаг 2 (200 или 422)
```
Шаг 2 — быстрый путь; корректность при гонке обеспечивает шаг 5 (уникальный индекс).

### 5.2 Вебхук банка
```
POST /webhooks/bank
 1. verify_signature (dependency, по сырым байтам тела) → 401        [бонус 1]
 2. Pydantic валидирует body → 422
 3. SELECT ... FROM payments WHERE id = :id FOR UPDATE → нет → 404
 4. ensure_transition_allowed(current, new) → InvalidTransitionError → 409
 5. UPDATE status, updated_at; COMMIT → 200 {"result": "ok"}
```
`FOR UPDATE` сериализует параллельные вебхуки по одному платежу: второй ждёт коммита первого и
проверяет переход уже от нового статуса.

## 6. Ошибки
Доменные исключения (`domain/errors.py`) → HTTP в одном месте (`api/errors.py`):

| Исключение | HTTP | Тело |
|---|---|---|
| `PaymentNotFoundError` | 404 | `{"detail": "Payment not found"}` |
| `InvalidTransitionError` | 409 | `{"error": "invalid_transition"}` |
| `UnknownTariffError` | 422 | формат FastAPI, `loc: ["body","tariff_id"]` |
| `UnknownPromoCodeError` | 422 | формат FastAPI, `loc: ["body","promo_code"]` |
| `IdempotencyKeyReusedError` | 422 | формат FastAPI, `loc: ["header","Idempotency-Key"]` |
| неверная подпись | 401 | `{"detail": "Invalid signature"}` (`HTTPException` в dependency) |

## 7. Транзакции и сессии (async)
- `async_sessionmaker(engine, expire_on_commit=False)`.
- Dependency `get_session` отдаёт одну сессию на запрос; коммит делает **сервис** в конце use-case'а.
- Никакого lazy loading: всё, что нужно, загружается явно (`select(...)`), связи не используются в ответах.
- Ответы строятся из ORM-объекта через `PaymentOut.model_validate(obj)` (`from_attributes=True`).

## 8. Тестовая инфраструктура
- Отдельная БД `kvitto_test` в том же Postgres (создаётся `docker/postgres/init.sql`; в CI — service-контейнер).
- Сессия pytest: `alembic upgrade head` один раз — заодно проверяются миграции и сид тарифов.
- Каждый тест: соединение → внешняя транзакция → `AsyncSession(bind=conn, join_transaction_mode="create_savepoint")`,
  dependency `get_session` переопределена, в конце — rollback. Тесты изолированы и не чистят таблицы.
- Клиент: `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
- `pytest-asyncio`: `asyncio_mode = "auto"`, единый event loop на сессию для фикстур и тестов
  (иначе asyncpg-соединение «живёт» в другом loop'е → ошибки).
- Тесты на гонку идемпотентности не помещаются в схему с откатом: им нужны отдельные соединения.
  Они лежат в `tests/services/test_payments_concurrency.py`, коммитят по-настоящему и удаляют
  свои строки по ключу.

## 9. Окружение и запуск
- `docker compose up` — `db` (postgres:16-alpine, healthcheck) + `app` (`alembic upgrade head && uvicorn`), порт 8000.
- Локально: `uv sync`, `docker compose up -d db`, `uv run alembic upgrade head`, `uv run uvicorn app.main:app --reload`.
- Тесты: `docker compose up -d db && uv run pytest`.
- Проверки: `uv run ruff check . && uv run ruff format --check . && uv run mypy .`.

## 10. План реализации
Каждый пункт — отдельная ветка и PR. Пункт готов, когда выполнен Definition of Done из CLAUDE.md.

| # | Ветка | Содержание |
|---|---|---|
| 0 | `chore/bootstrap` | git, pyproject (uv), ruff/mypy/pytest конфиг, `app/main.py` с `/health`, config, Dockerfile, compose, Alembic async env, `.env.example`, conftest-каркас |
| 1 | `feat/domain` | test-first: `money.py` (скидка, график), `promo.py`, `status.py`, `errors.py`, `enums.py` |
| 2 | `feat/db-schema` | модели, миграции `0001` (схема) и `0002` (сид тарифов), тестовая инфраструктура БД |
| 3 | `feat/tariffs` | `GET /tariffs` |
| 4 | `feat/payments` | `POST /payments` (вкл. идемпотентность), `GET /payments/{id}` |
| 5 | `feat/webhook` | `POST /webhooks/bank` |
| 6 | `docs/mvp` | README с curl-примерами, сверка с ТЗ, DECISIONS. **MVP готов** |
| 7 | `feat/webhook-signature` | бонус: HMAC `X-Signature` |
| 8 | `feat/payments-list` | бонус: `GET /payments` с фильтрами |
| 9 | `ci/github-actions` | бонус: ruff + mypy + pytest на push |
