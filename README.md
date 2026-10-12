# baseline-attempt-2

## Pipeline stages

```bash
python main.py --stage collect            # index catalog pages
python main.py --stage visit              # parse artwork pages
python main.py --stage export-top-artists # export artists with expensive collections
```

### export-top-artists

Выбирает художников, у которых суммарная стоимость картин в базе превышает порог,
и сохраняет их в JSON (записи отсортированы по убыванию суммы):

```bash
python main.py --stage export-top-artists --min-total-price 3000000 --output top_artists.json
```

| Аргумент | По умолчанию | Описание |
| --- | --- | --- |
| `--min-total-price` | `3000000` | Минимальная суммарная стоимость работ художника |
| `--output` | `top_artists.json` | Файл для записи результата |

Пример записи:

```json
{
  "name": "Художник",
  "total_price": 15600000.0,
  "artwork_count": 12,
  "art_types": ["живопись"],
  "techniques": ["акрил", "масло"]
}
```
