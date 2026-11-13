# Keitaro wrapper

Обёртка над [Keitaro](https://keitaro.io) Admin API v1: создание кампаний по шаблону и редактор офферов в потоке.
FastAPI + SQLAlchemy 2 + Alembic, фронт — HTML и ванильный JS без сборки.

## Что умеет

**1. Создание кампании.** На вход: название, гео (коды стран через запятую), оффер (поиск с автодополнением
по названию или ID). Создаёт в Keitaro кампанию с группой, доменом и источником и двумя потоками:

| # | Поток | Фильтр | Куда |
|---|---|---|---|
| 1 | `AU,MX -> Google` | страна ∈ указанные | редирект на `https://google.com` |
| 2 | `Offers` | — (весь остальной трафик) | выбранный оффер, 100% |

Название получает префикс `test_ivanov_`, если его нет (`CAMPAIGN_PREFIX`). Если поток не создался, кампания
удаляется: в трекере не остаётся полусобранных кампаний.

**2. Редактор кампании.** Повторяет логику редактора из видео ТЗ:

- **Загрузить потоки из Keitaro** — свежие потоки, офферы, доли и статистика (клики, конверсии, доход за 7 дней);
- **Добавить** оффер — доли пересчитываются поровну: 2 → 50/50, 3 → 34/33/33, 4 → 25×4;
- **Remove** — оффер получает 0%, остаётся в списке серым, рядом кнопка **Bring back**;
- **📌 закрепить** долю — при пересчёте она не меняется, остаток делится между остальными
  (закреплено 25% → остальным 38/37);
- **клик по доле** — ввести вручную, доля сразу закрепляется;
- любые изменения — сначала черновик (жёлтая карточка, сумма долей). В Keitaro уходят только по
  **Push to Keitaro**, **Cancel** откатывает черновик.

Сумму долей = 100% проверяет сервер: Keitaro сам принимает и 60 + 50.

## Запуск

Нужен Python 3.11+.

```bash
git clone https://github.com/seshb0y/keitaro-wrapper.git
cd keitaro-wrapper
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # вписать KEITARO_API_KEY (Keitaro → Профиль → API ключи)
alembic upgrade head          # создать схему БД
uvicorn app.main:app --reload # http://127.0.0.1:8000
```

Тесты (Keitaro подменён фейком на `httpx.MockTransport`, в трекер ничего не пишут):

```bash
pytest
```

## Миграции

Схема БД создаётся и меняется только через Alembic, `create_all()` в приложении нет.
URL базы берётся из `DATABASE_URL` в `.env` (по умолчанию SQLite-файл `keitaro_wrapper.db`).

```bash
alembic upgrade head                              # применить все миграции
alembic revision --autogenerate -m "что изменили" # после правки app/models.py
alembic downgrade -1                              # откатить последнюю
```

Для SQLite включён `render_as_batch`, поэтому `ALTER COLUMN` в автогенерированных миграциях работает.

## Настройки (.env)

| Переменная | Зачем |
|---|---|
| `KEITARO_URL`, `KEITARO_API_KEY` | адрес трекера и ключ Admin API |
| `DATABASE_URL` | SQLAlchemy URL, по умолчанию `sqlite:///./keitaro_wrapper.db` |
| `CAMPAIGN_PREFIX` | префикс имён кампаний, `test_ivanov_` |
| `DEFAULT_GROUP_ID`, `DEFAULT_DOMAIN_ID`, `DEFAULT_TRAFFIC_SOURCE_ID` | что подставить в форме по умолчанию |
| `GEO_REDIRECT_URL` | куда первый поток шлёт трафик из выбранных стран, `https://google.com` |

## Как устроено

```
app/
  keitaro.py   клиент Admin API (httpx): кампании, потоки, офферы, справочники, отчёты
  shares.py    правила долей: rebalance() и validate() — чистые функции, покрыты тестами
  service.py   создание кампании, сборка данных редактора, push
  main.py      FastAPI: страницы и JSON API
  models.py    SQLAlchemy-модели
  static/, templates/   фронт
migrations/    Alembic
tests/         pytest
```

Источник правды по кампаниям, потокам и долям — Keitaro. В своей БД хранится только то, чего в Keitaro нет:

- `campaigns` — кампании, созданные через обёртку: гео, оффер, ID потоков;
- `stream_offer_states` — закреплена ли доля и снятые офферы. Keitaro удаляет оффер из потока совсем,
  а «Bring back» должен работать и после перезагрузки страницы;
- `push_log` — история отправок: доли до и после.

Пересчёт черновика делает сервер (`POST /api/rebalance`), а не дублированный JS: правила в одном месте,
и они же покрыты тестами.

API: `GET /api/meta`, `GET /api/offers?q=`, `GET|POST /api/campaigns`, `GET /api/campaigns/{id}`,
`POST /api/rebalance`, `PUT /api/streams/{id}/offers`. Интерактивная документация — `/docs`.

## Ограничения тестового аккаунта

- **Домены и источники** этому пользователю недоступны. `GET /domains`, `/domains/deleted`,
  `/groups?type=domains` и `/traffic_sources` отвечают `200 []`. `POST /domains` и `POST /traffic_sources`
  отвечают `403 You have no permission … Domains/TrafficSources`, то есть создать свои тоже нельзя.
  В интерфейсе Keitaro у этого пользователя оба списка пустые («No options»), и во всех кампаниях
  других кандидатов `domain_id = null`, `traffic_source_id = 0`. Без домена кампания работает
  на домене трекера (`tlgk.host`).
  Если доступ появится, домен и источник выбираются в форме (списки берутся из API) или задаются в `.env`
  и уходят в Keitaro как `domain_id` / `traffic_source_id`.
- Доступна одна группа кампаний — `VZ adrobot test`, она стоит по умолчанию.
- Аккаунт общий с другими кандидатами, поэтому список кампаний по умолчанию фильтруется по префиксу.
