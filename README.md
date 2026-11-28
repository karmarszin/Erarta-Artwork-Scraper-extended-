# Erarta Artwork ETL Pipeline

Образовательный микро-ETL пайплайн: сбор, нормализация и хранение данных о произведениях искусства с витрины музея «Эрарта».

SQLite используется как шина состояний (очередь задач): статусы `pending` / `done` / `error` позволяют прерывать процесс и продолжать без повторного обхода уже обработанных URL.

## Слои

| Слой | Где | Ответственность |
| --- | --- | --- |
| CLI / handlers | `erarta_scraper/cli.py`, `main.py` | аргументы, логирование, запуск стадий |
| Pipeline (orchestration) | `erarta_scraper/pipeline/` | collect / visit, батчи, лимиты |
| Domain | `erarta_scraper/domain/` | статусы, DTO, чистые парсеры |
| Scraping | `erarta_scraper/scraping/` | WebDriver, селекторы, retry, rate limit |
| Data access | `erarta_scraper/db/` | модели, session factory, repositories |

Корневые `models.py`, `link_scraper.py`, `link_visitor.py` — тонкие обёртки для старых команд запуска.

## Конвенции (обнаружимые в коде)

1. **Очередь в БД, не в памяти.** Новая карточка всегда `ArtworkStatus.PENDING`; воркер меняет статус на `DONE` или `ERROR`.
2. **Идемпотентный enqueue.** `ArtworkRepository.enqueue_urls` делает `ON CONFLICT DO NOTHING` по `url` и не сбрасывает уже обработанные строки.
3. **Get-or-create с кэшем.** `ArtistRepository.get_or_create_id` сначала смотрит in-memory cache, затем БД, затем `flush()`.
4. **Батч-коммит.** Visit фиксирует транзакцию целиком на пачку, а не на каждую картину. Исключение — `retry-failed`: там коммит идёт после каждой карточки, чтобы не терять уже восстановленные строки при падении на следующей.
5. **Иерархия ошибок.** `ScraperError` → `ParseError` / `BrowserError` / `QueueError`; retry только на сетевые/браузерные сбои.
6. **Локаторы отдельно от парсинга.** XPath/CSS живут в `scraping/selectors.py`; `details_from_text_getter` принимает любой `locator → text` и набор локаторов, который инжектит scraping-слой.
7. **Конфиг из env.** Префикс `ERARTA_*` (`ERARTA_PAGES`, `ERARTA_HEADLESS`, `ERARTA_DB_PATH`, …), CLI перекрывает env.
8. **Логгер `erarta`.** Библиотечный код не вызывает `print`.
9. **Пауза между запросами.** `Pace` в `BrowserSession.get`.

## Схема БД

```text
artists (id, name UNIQUE)
artworks (id, url UNIQUE, title, artist_id FK,
          price, year, size, art_type, genre, technique, baguette,
          status, updated_at)
```

WAL и `PRAGMA foreign_keys=ON` включаются при создании файлового engine.

## Установка

```
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Нужен Google Chrome (Selenium 4 подтягивает ChromeDriver сам).

## Запуск

```
python main.py
python main.py --stage collect --pages 10
python main.py --stage visit --limit 50 --batch-size 20 --headless
python main.py --stage retry-failed --max-retries 20 --report-file retry_report.csv
python models.py
```

`retry-failed` повторно обходит карточки со статусом `error`: до `--max-retries`
штук за запуск (по умолчанию 20, `0` — только создать пустой отчёт). Каждая
карточка парсится тем же retry-механизмом, что и в `visit`, после чего
проверяется наличие плашки со старой ценой `.old-price-tag`. Успешные карточки
получают статус `done` и коммитятся сразу по одной, сбойные остаются `error` и
не прерывают обход. В CSV `--report-file` (по умолчанию `retry_report.csv`)
пишется строка на попытку с колонками `url, old_status, new_status,
has_discount`; файл перезаписывается при каждом запуске. Итоговая статистика
(`attempts`, `restored`) выводится в логгер `erarta`.

Переменные окружения: `ERARTA_DB_PATH`, `ERARTA_PAGES`, `ERARTA_BATCH_SIZE`, `ERARTA_HEADLESS`, `ERARTA_REQUEST_DELAY`.

## Тесты

```
pytest
```

Тесты ходят в in-memory SQLite и подменяют браузер; живой сайт не дергается.

*Проект учебный. Соблюдайте robots.txt и разумную нагрузку на витрину.*
