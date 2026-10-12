#!/usr/bin/env python3
"""check.py — статический чекер задачи «экспорт авторов с дорогой коллекцией».

Запуск:
    python check.py
    python check.py --output top_artists.json --min-total-price 3000000

Что проверяется (без LLM, только чтение файлов/БД):
  1. Нарушения слоёв (таблица «Слои» в README.md) — по AST-импортам.
  2. Конвенции из README.md (пункты 5-9): нет print в библиотеке,
     env-префикс ERARTA_*, локаторы только в scraping/, логгер erarta,
     экспорт не ходит в браузер/сеть.
  3. Обвязка задачи: --stage export-top-artists, --min-total-price
     (default 3 000 000), --output (default top_artists.json), наличие
     реализации, логирование числа записей, сортировка по убыванию,
     JSON на выходе, тест и упоминание в README.
  4. Данные: сверка tests/expensive_artists.json с БД (read-only) и с
     файлом результата: количество авторов, имена (strip()), общие суммы,
     количество картин; уникальные стили/техники — мягкая сверка.

Итог: «нарушений: N» + список файлов/строк. Код выхода 1, если N > 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from pathlib import Path

try:  # Windows console в cp1251
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".idea", ".vscode"}

STAGE = "export-top-artists"
MIN_PRICE_OPT = "--min-total-price"
OUTPUT_OPT = "--output"
DEFAULT_MIN_TOTAL_PRICE = 3_000_000
DEFAULT_OUTPUT = "top_artists.json"
PRICE_TOLERANCE = 0.01


# --------------------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------------------
class Report:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, str]] = []  # (раздел, kind, текст)
        self._section = ""

    def section(self, title: str) -> None:
        self._section = title
        print(f"\n== {title} ==")

    def ok(self, text: str) -> None:
        print(f"  [ok]   {text}")

    def fail(self, text: str) -> None:
        self.entries.append((self._section, "FAIL", text))
        print(f"  [FAIL] {text}")

    def warn(self, text: str) -> None:
        self.entries.append((self._section, "warn", text))
        print(f"  [warn] {text}")

    @property
    def violations(self) -> list[tuple[str, str, str]]:
        return [e for e in self.entries if e[1] == "FAIL"]

    @property
    def warnings(self) -> list[tuple[str, str, str]]:
        return [e for e in self.entries if e[1] == "warn"]


# --------------------------------------------------------------------------------------
# файлы
# --------------------------------------------------------------------------------------
def iter_py_files() -> list[Path]:
    files = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")  # переживает BOM
    except OSError:
        return ""


_PARSE_CACHE: dict[str, ast.AST | None] = {}
_WARNED: set[str] = set()


def parse_tree(path: Path, report: Report | None = None) -> ast.AST | None:
    key = rel(path)
    if key in _PARSE_CACHE:
        return _PARSE_CACHE[key]
    src = read_text(path)
    tree: ast.AST | None
    try:
        tree = ast.parse(src, filename=key) if src else None
    except SyntaxError as exc:
        tree = None
        if report is not None and key not in _WARNED:
            _WARNED.add(key)
            report.warn(f"{key}: не разбирается ({exc.msg}) — часть проверок пропущена")
    _PARSE_CACHE[key] = tree
    return tree


# --------------------------------------------------------------------------------------
# 1. Слои
# --------------------------------------------------------------------------------------
LAYER_PREFIXES = [
    ("erarta_scraper/domain/", "domain"),
    ("erarta_scraper/db/", "db"),
    ("erarta_scraper/scraping/", "scraping"),
    ("erarta_scraper/pipeline/", "pipeline"),
    ("erarta_scraper/cli.py", "cli"),
    ("erarta_scraper/analytics.py", "analytics"),
    ("erarta_scraper/config.py", "support"),
    ("erarta_scraper/logging_setup.py", "support"),
    ("erarta_scraper/exceptions.py", "exceptions"),
    ("erarta_scraper/__init__.py", "package"),
    ("tests/", "tests"),
    ("main.py", "cli"),
    ("models.py", "cli"),
    ("link_scraper.py", "cli"),
    ("link_visitor.py", "cli"),
]

MODULE_LAYERS = sorted(
    [
        ("erarta_scraper.domain", "domain"),
        ("erarta_scraper.db", "db"),
        ("erarta_scraper.scraping", "scraping"),
        ("erarta_scraper.pipeline", "pipeline"),
        ("erarta_scraper.cli", "cli"),
        ("erarta_scraper.analytics", "analytics"),
        ("erarta_scraper.config", "support"),
        ("erarta_scraper.logging_setup", "support"),
        ("erarta_scraper.exceptions", "exceptions"),
        ("erarta_scraper", "package"),
    ],
    key=lambda pair: -len(pair[0]),
)

ALL_LAYERS = {"domain", "exceptions", "support", "db", "scraping", "pipeline",
              "analytics", "cli", "package", "tests", "other"}

# кому разрешено импортировать внутренние слои
ALLOWED: dict[str, set[str]] = {
    "domain": {"domain", "exceptions"},          # чистый домен: только DTO/статусы/парсеры
    "exceptions": set(),                          # иерархия ошибок, ничего не знает
    "support": set(),                             # config / logging_setup
    "db": {"domain", "db", "support", "exceptions"},
    "scraping": {"domain", "scraping", "support", "exceptions"},
    "pipeline": {"domain", "db", "scraping", "pipeline", "support", "exceptions"},
    "analytics": {"domain", "db", "support", "exceptions"},
    "cli": ALL_LAYERS,
    "package": ALL_LAYERS,
    "tests": ALL_LAYERS,
    "other": ALL_LAYERS,                          # корневые точки входа
}

LAYER_TITLES = {
    "domain": "domain/ (чистый домен)",
    "db": "db/ (доступ к данным)",
    "scraping": "scraping/ (браузер)",
    "pipeline": "pipeline/ (оркестрация)",
    "cli": "cli",
    "analytics": "analytics/ (сервисы)",
    "support": "config/logging_setup",
    "exceptions": "exceptions",
}

# утечки сторонних библиотек в слой (README: слои и их ответственность)
LEAK_RULES: dict[str, dict[str, str]] = {
    "domain": {
        "sqlalchemy": "domain не должен зависеть от SQLAlchemy (модели живут в db/)",
        "selenium": "domain не должен зависеть от Selenium",
    },
    "db": {"selenium": "db/ не должен импортировать Selenium (браузер — в scraping/)"},
    "scraping": {"sqlalchemy": "scraping/ не должен зависеть от SQLAlchemy (запросы — в db/)"},
    "pipeline": {"selenium": "pipeline использует scraping.BrowserSession, а не selenium напрямую"},
    "cli": {"selenium": "cli не должен импортировать Selenium напрямую"},
}


def layer_of_file(path: Path) -> str:
    r = rel(path)
    for prefix, layer in LAYER_PREFIXES:
        if r == prefix or r.startswith(prefix):
            return layer
    if r.startswith("erarta_scraper/"):
        return "analytics"  # новый модуль верхнего уровня = сервисный слой
    return "other"


def layer_of_module(module: str) -> str | None:
    for prefix, layer in MODULE_LAYERS:
        if module == prefix or module.startswith(prefix + "."):
            return layer
    return None


def module_and_package(path: Path) -> tuple[str, str]:
    """('erarta_scraper.db.repositories', 'erarta_scraper.db')."""
    stem = rel(path)[:-3]
    if stem.endswith("__init__"):
        pkg = stem[: -len("__init__")].rstrip("/")
        return pkg, pkg
    if "/" in stem:
        return stem.replace("/", "."), stem.rsplit("/", 1)[0].replace("/", ".")
    return stem, stem


def resolve_relative(package: str, level: int, module: str | None) -> str:
    parts = package.split(".") if package else []
    base = parts[: len(parts) - (level - 1)] if level > 1 else parts
    if module:
        base = base + module.split(".")
    return ".".join(base)


def iter_imports(tree: ast.AST, path: Path):
    """(node, полное_имя_модуля)."""
    _, package = module_and_package(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                yield node, resolve_relative(package, node.level, node.module)
            elif node.module:
                yield node, node.module


def check_layers(report: Report, files: list[Path]) -> None:
    report.section("1. Слои (README «Слои»)")
    problems = 0
    for path in files:
        r = rel(path)
        if r.startswith("tests/"):
            continue
        tree = parse_tree(path, report)
        if tree is None:
            continue
        src_layer = layer_of_file(path)
        allowed = ALLOWED.get(src_layer, ALL_LAYERS)
        for node, module in iter_imports(tree, path):
            top = module.split(".")[0]
            if top == "erarta_scraper":
                target = layer_of_module(module)
                if target is None:
                    continue
                if target == src_layer:
                    continue
                if target not in allowed:
                    problems += 1
                    report.fail(
                        f"{r}:{node.lineno} — {LAYER_TITLES.get(src_layer, src_layer)} "
                        f"импортирует {LAYER_TITLES.get(target, target)} (`{module}`)"
                    )
                # cli импортируется только точками входа
                if target == "cli" and r not in {"main.py"}:
                    problems += 1
                    report.fail(f"{r}:{node.lineno} — импорт `erarta_scraper.cli` разрешён только из main.py")
            if src_layer in LEAK_RULES and top in LEAK_RULES[src_layer]:
                problems += 1
                report.fail(f"{r}:{node.lineno} — {LEAK_RULES[src_layer][top]} (`import {top}`)")
    if problems == 0:
        report.ok("нарушений слоёв не найдено")


# --------------------------------------------------------------------------------------
# 2. Конвенции README
# --------------------------------------------------------------------------------------
def check_conventions(report: Report, files: list[Path]) -> None:
    report.section("2. Конвенции (README «Конвенции»)")
    problems = 0

    for path in files:
        r = rel(path)
        if not r.startswith("erarta_scraper/"):
            continue
        tree = parse_tree(path, report)
        if tree is None:
            continue
        src = read_text(path)

        # №8: библиотечный код не вызывает print
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                problems += 1
                report.fail(f"{r}:{node.lineno} — print() в библиотечном коде (конвенция №8, логгер `erarta`)")

        # №7: конфиг из env с префиксом ERARTA_*
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if fname not in {"getenv", "environ.get"}:
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                name = node.args[0].value
                if not name.startswith("ERARTA_"):
                    problems += 1
                    report.fail(f"{r}:{node.lineno} — env-переменная `{name}` без префикса ERARTA_ (конвенция №7)")

        # №6: XPath/CSS-локаторы живут в scraping/
        if re.search(r"By\.(XPATH|CSS_SELECTOR)", src) and not r.startswith("erarta_scraper/scraping/"):
            for i, line in enumerate(src.splitlines(), 1):
                if re.search(r"By\.(XPATH|CSS_SELECTOR)", line):
                    problems += 1
                    report.fail(f"{r}:{i} — локатор вне scraping/ (конвенция №6)")

        # №8: логгер один — `erarta`
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value not in {"erarta"}
            ):
                problems += 1
                report.fail(f"{r}:{node.lineno} — логгер `{node.args[0].value}` вместо `erarta` (конвенция №8)")

    if problems == 0:
        report.ok("нарушений конвенций не найдено")


# --------------------------------------------------------------------------------------
# 3. Обвязка задачи
# --------------------------------------------------------------------------------------
def add_argument_calls(tree: ast.AST) -> dict[str, tuple[dict[str, ast.expr], ast.Call]]:
    found: dict[str, tuple[dict[str, ast.expr], ast.Call]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("-"):
                found[arg.value] = (kwargs, node)
    return found


def literal(node: ast.expr | None):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def number_equal(value, expected: float) -> bool:
    if value is None:
        return False
    try:
        return abs(float(str(value).replace(" ", "").replace("\xa0", "")) - expected) < 1e-6
    except (TypeError, ValueError):
        return False


EXPORT_MARKERS = re.compile(
    r"export-top-artists|export_top_artists|min_total_price|top_artists\.json|def\s+\w*export\w*\s*\(",
    re.IGNORECASE,
)
AGGREGATION = (re.compile(r"func\.sum\s*\("), re.compile(r"\.group_by\s*\("))


def looks_like_export(src: str) -> bool:
    """Модуль похож на реализацию экспорта, если в нём есть маркеры задачи
    либо агрегация суммы по художникам."""
    if EXPORT_MARKERS.search(src):
        return True
    return all(p.search(src) for p in AGGREGATION) and "price" in src and "Artist" in src


def check_task(report: Report, files: list[Path], threshold_default_ok: bool = True) -> list[Path]:
    """Возвращает файлы с реализацией экспорта."""
    report.section(f"3. Задача: --stage {STAGE}")

    cli_path = ROOT / "erarta_scraper" / "cli.py"
    cli_src = read_text(cli_path)
    cli_tree = parse_tree(cli_path, report)
    opts = add_argument_calls(cli_tree) if cli_tree else {}

    # --stage choices
    if "--stage" not in opts:
        report.fail("cli.py: нет аргумента --stage")
    else:
        choices = literal(opts["--stage"][0].get("choices"))
        if isinstance(choices, (list, tuple)) and STAGE in [str(c) for c in choices]:
            report.ok(f"--stage choices содержат `{STAGE}`")
        else:
            report.fail(f"cli.py: в choices аргумента --stage нет `{STAGE}` (сейчас: {choices})")

    # --min-total-price
    if MIN_PRICE_OPT not in opts:
        report.fail(f"cli.py: нет аргумента {MIN_PRICE_OPT} (по умолчанию {DEFAULT_MIN_TOTAL_PRICE:,})".replace(",", " "))
    else:
        kwargs = opts[MIN_PRICE_OPT][0]
        default = literal(kwargs.get("default"))
        if default is None:
            report.fail(f"cli.py: у {MIN_PRICE_OPT} нет default (нужен {DEFAULT_MIN_TOTAL_PRICE})")
        elif number_equal(default, DEFAULT_MIN_TOTAL_PRICE):
            report.ok(f"{MIN_PRICE_OPT} default = {default}")
        else:
            report.fail(f"cli.py: {MIN_PRICE_OPT} default = {default!r}, ожидалось {DEFAULT_MIN_TOTAL_PRICE}")

    # --output
    if OUTPUT_OPT not in opts:
        report.fail(f"cli.py: нет аргумента {OUTPUT_OPT} (по умолчанию {DEFAULT_OUTPUT})")
    else:
        default = literal(opts[OUTPUT_OPT][0].get("default"))
        if default == DEFAULT_OUTPUT:
            report.ok(f"{OUTPUT_OPT} default = {default}")
        else:
            report.fail(f"cli.py: {OUTPUT_OPT} default = {default!r}, ожидалось {DEFAULT_OUTPUT!r}")

    # диспетчеризация стадии
    if re.search(rf"args\.stage.{{0,120}}{re.escape(STAGE)}", cli_src, re.S):
        report.ok(f"cli.py диспетчеризует стадию `{STAGE}`")
    else:
        report.fail(f"cli.py: стадия `{STAGE}` объявлена, но не запускается из main()")

    # слой: в cli не должно быть запросов к БД
    if re.search(r"\bselect\s*\(|func\.sum\s*\(|session\.execute\s*\(", cli_src):
        report.fail("cli.py: SQL/агрегация в слое CLI (README: cli — только аргументы, логирование, запуск стадий)")

    # реализация
    candidates: list[Path] = []
    for path in files:
        r = rel(path)
        if not r.startswith("erarta_scraper/") or r.endswith("cli.py"):
            continue
        src = read_text(path)
        if looks_like_export(src):
            candidates.append(path)

    if not candidates:
        report.fail(
            "не найден модуль с логикой экспорта (ожидается файл в erarta_scraper/ со "
            "стадией/аргументами экспорта; cli.py — только запуск)"
        )
        return []

    for path in candidates:
        r = rel(path)
        src = read_text(path)
        print(f"  -- реализация: {r}")

        # выборка художников с суммой > порога
        if re.search(r"func\.sum\s*\(", src) and re.search(r"price", src):
            report.ok(f"{r}: агрегация суммы по price")
        else:
            report.fail(f"{r}: нет агрегации func.sum(price) по художникам")

        if re.search(r"having\s*\(", src, re.I) or (">" in src and re.search(r"min_total_price|threshold", src)):
            report.ok(f"{r}: фильтр «сумма > порога»")
        else:
            report.fail(f"{r}: нет сравнения суммы с --min-total-price (having/`>` порога)")

        # сортировка по убыванию
        if re.search(r"\.desc\s*\(", src) or re.search(r"reverse\s*=\s*True", src):
            report.ok(f"{r}: сортировка по убыванию суммы")
        else:
            report.fail(f"{r}: нет сортировки по убыванию общей суммы (.desc()/reverse=True)")

        # сохранение JSON
        if re.search(r"json\.(dump|dumps)\s*\(", src) or re.search(r"\.write_text\s*\(", src):
            report.ok(f"{r}: результат сохраняется в JSON")
        else:
            report.fail(f"{r}: нет сохранения результата в JSON (json.dump / write_text)")

        # логирование количества записей
        logged = False
        tree = parse_tree(path, report)
        if tree is not None:
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in {"debug", "info", "warning", "error"}:
                    continue
                seg = ast.get_source_segment(src, node) or ""
                if re.search(r"len\s*\(|count|запис|export|record|len\b", seg, re.I):
                    logged = True
                    break
        if logged:
            report.ok(f"{r}: залогировано количество выгруженных записей")
        else:
            report.fail(f"{r}: не залогировано количество выгруженных записей (log.info(... len/count))")

        # стили и техники
        if re.search(r"art_type", src) and re.search(r"technique", src):
            report.ok(f"{r}: собираются art_type и technique")
        else:
            report.fail(f"{r}: не собираются уникальные art_type/technique")

        # экспорт не должен ходить в браузер
        if re.search(r"selenium|BrowserSession", src):
            report.fail(f"{r}: экспорт должен читать БД, а не WebDriver (конвенция: очередь/данные — в БД)")

    return candidates


def check_tests_and_docs(report: Report, impl_files: list[Path]) -> None:
    report.section("4. Тесты и документация")
    tests_src = "\n".join(read_text(p) for p in sorted((ROOT / "tests").glob("*.py")))
    markers = (STAGE, "min_total_price", "export_top_artists", "top_artists.json")
    if not any(m in tests_src for m in markers):
        report.fail(f"tests/: нет теста на `{STAGE}` / --min-total-price / --output")
    else:
        report.ok(f"в tests/ есть тест на `{STAGE}`")

    for path in impl_files:
        dotted = module_and_package(path)[0]
        if dotted in tests_src:
            report.ok(f"{dotted} покрыт тестом")
        elif any(m in tests_src for m in markers):
            report.ok("логика экспорта упоминается в tests/")
        else:
            report.fail(f"модуль {dotted} не покрыт тестом в tests/")

    readme = read_text(ROOT / "README.md")
    if STAGE in readme:
        report.ok(f"README.md описывает стадию `{STAGE}`")
    else:
        report.fail(f"README.md: стадия `{STAGE}` не описана (секция «Запуск»)")
    if MIN_PRICE_OPT in readme:
        report.ok(f"README.md описывает {MIN_PRICE_OPT}")
    else:
        report.warn(f"README.md: {MIN_PRICE_OPT} не упомянут")


# --------------------------------------------------------------------------------------
# 4. Данные
# --------------------------------------------------------------------------------------
def norm_name(value) -> str:
    return "" if value is None else str(value).strip()


def norm_total(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).replace("\xa0", "").replace(" ", "").replace("₽", "").replace("руб.", "").strip()
    txt = txt.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    return float(m.group()) if m else None


def norm_count(value) -> int | None:
    total = norm_total(value)
    return int(total) if total is not None else None


def norm_tokens(value) -> set[str]:
    """Строку «холст, акрил,холст, смешанная техника» или список — в множество токенов."""
    if value is None:
        return set()
    items = value if isinstance(value, list) else [value]
    out: set[str] = set()
    for item in items:
        for part in str(item).split(","):
            token = part.strip().casefold()
            if token:
                out.add(token)
    return out


def pick(rec: dict, *names: str):
    lowered = {str(k).lower(): v for k, v in rec.items()}
    for name in names:
        if name in rec:
            return rec[name]
        if name in lowered:
            return lowered[name]
    return None


def normalize_records(data, report: Report, label: str) -> list[dict] | None:
    if data is None:
        return None
    if isinstance(data, dict):
        for key in ("artists", "items", "results", "data", "rows", "records"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            lists = [v for v in data.values() if isinstance(v, list)]
            data = lists[0] if len(lists) == 1 else None
    if not isinstance(data, list):
        report.fail(f"{label}: ожидался JSON-список записей")
        return None
    rows = []
    for i, rec in enumerate(data):
        if not isinstance(rec, dict):
            report.fail(f"{label}: запись #{i} не объект")
            continue
        name = norm_name(pick(rec, "name", "artist", "artist_name"))
        total = norm_total(pick(rec, "total_price", "total", "sum", "total_sum", "price_sum", "sum_price"))
        count = norm_count(pick(rec, "artworks_count", "count", "works_count", "artworks", "n_artworks"))
        types = pick(rec, "unique_art_types", "art_types", "styles", "unique_styles")
        techs = pick(rec, "unique_techniques", "techniques", "unique_tech")
        missing = []
        if not name:
            missing.append("name")
        if total is None:
            missing.append("total_price")
        if count is None:
            missing.append("artworks_count")
        if types is None:
            missing.append("unique_art_types")
        if techs is None:
            missing.append("unique_techniques")
        if missing:
            report.fail(f"{label}: запись #{i} без полей {', '.join(missing)}")
        rows.append({"name": name, "total": total, "count": count, "types": types, "techs": techs})
    return rows


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        return exc


def query_expected(db_path: Path, threshold: float) -> list[dict] | None:
    """Эталон: художники с суммой картин > порога, отсортированные по убыванию."""
    if not db_path.exists():
        return None
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            """
            SELECT ar.name,
                   SUM(a.price) AS total_price,
                   COUNT(*)     AS artworks_count
              FROM artworks a
              JOIN artists ar ON ar.id = a.artist_id
             WHERE a.price IS NOT NULL
             GROUP BY ar.id
            HAVING SUM(a.price) > ?
             ORDER BY total_price DESC
            """,
            (threshold,),
        ).fetchall()
    finally:
        conn.close()
    return [{"name": norm_name(n), "total": float(t), "count": int(c)} for n, t, c in rows]


def query_styles(db_path: Path, threshold: float) -> dict[str, tuple[set[str], set[str]]]:
    if not db_path.exists():
        return {}
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        names = {
            norm_name(n)
            for n, in conn.execute(
                "SELECT ar.name FROM artworks a JOIN artists ar ON ar.id = a.artist_id "
                "WHERE a.price IS NOT NULL GROUP BY ar.id HAVING SUM(a.price) > ?",
                (threshold,),
            ).fetchall()
        }
        data: dict[str, tuple[set[str], set[str]]] = {}
        for name, art_type, technique in conn.execute(
            "SELECT ar.name, a.art_type, a.technique FROM artworks a "
            "JOIN artists ar ON ar.id = a.artist_id WHERE a.price IS NOT NULL"
        ).fetchall():
            key = norm_name(name)
            types, techs = data.get(key, (set(), set()))
            types |= norm_tokens(art_type)
            techs |= norm_tokens(technique)
            data[key] = (types, techs)
    finally:
        conn.close()
    return {k: v for k, v in data.items() if k in names}


def compare_rows(report: Report, label: str, actual: list[dict], expected: list[dict]) -> None:
    """Сверка количества, имён (strip), сумм и количества картин по позициям."""
    if len(actual) != len(expected):
        report.fail(f"{label}: количество авторов {len(actual)} != {len(expected)}")

    exp_names = {r["name"] for r in expected}
    act_names = {r["name"] for r in actual}
    if act_names != exp_names:
        only_act = sorted(act_names - exp_names)
        only_exp = sorted(exp_names - act_names)
        if only_act:
            report.fail(f"{label}: лишние авторы: {', '.join(only_act)[:200]}")
        if only_exp:
            report.fail(f"{label}: отсутствуют авторы: {', '.join(only_exp)[:200]}")
    else:
        report.ok(f"{label}: имена совпадают после strip() ({len(actual)} шт.)")

    for i, (a, e) in enumerate(zip(actual, expected)):
        if a["name"] != e["name"]:
            report.fail(f"{label}: #{i}: имя {a['name']!r} != {e['name']!r} (после strip())")
        if a["total"] is None or e["total"] is None or abs(a["total"] - e["total"]) > PRICE_TOLERANCE:
            report.fail(f"{label}: #{i} ({e['name']}): сумма {a['total']} != {e['total']}")
        if a["count"] != e["count"]:
            report.fail(f"{label}: #{i} ({e['name']}): картин {a['count']} != {e['count']}")

    if all(a["total"] is not None and e["total"] is not None and abs(a["total"] - e["total"]) <= PRICE_TOLERANCE
           and a["count"] == e["count"] and a["name"] == e["name"]
           for a, e in zip(actual, expected)) and len(actual) == len(expected):
        report.ok(f"{label}: суммы и количество картин совпадают")


def check_sorted(report: Report, label: str, rows: list[dict]) -> None:
    totals = [r["total"] for r in rows]
    if any(t is None for t in totals):
        return
    if all(totals[i] >= totals[i + 1] for i in range(len(totals) - 1)):
        report.ok(f"{label}: отсортировано по убыванию суммы")
    else:
        report.fail(f"{label}: записи отсортированы не по убыванию total_price")


def check_threshold(report: Report, label: str, rows: list[dict], threshold: float) -> None:
    bad = [r["name"] for r in rows if r["total"] is None or r["total"] <= threshold]
    if bad:
        report.fail(f"{label}: сумма не превышает порог {threshold}: {', '.join(bad)[:200]}")
    else:
        report.ok(f"{label}: все суммы > {threshold}")


def soft_styles(report: Report, label: str, rows: list[dict], reference: dict[str, tuple[set[str], set[str]]],
                source: str) -> None:
    mismatches = []
    for row in rows:
        exp = reference.get(row["name"])
        if not exp:
            continue
        got_types, got_techs = norm_tokens(row["types"]), norm_tokens(row["techs"])
        if row["types"] is None or row["techs"] is None:
            continue
        if got_types != exp[0] or got_techs != exp[1]:
            mismatches.append(row["name"])
    if not reference:
        return
    if mismatches:
        report.warn(f"{label}: стили/техники отличаются от {source} у: {', '.join(mismatches)[:200]}")
    else:
        report.ok(f"{label}: стили и техники совпадают с {source} (мягкая сверка)")


def check_data(report: Report, out_path: Path, fixture_path: Path, db_path: Path, threshold: float) -> None:
    report.section("5. Данные: БД vs expensive_artists.json vs результат")

    expected = None
    try:
        expected = query_expected(db_path, threshold)
    except sqlite3.Error as exc:
        report.warn(f"не удалось прочитать {db_path.name}: {exc}")
    if expected is None:
        report.warn(f"{db_path.name} не найден — сверка только с эталоном")
    else:
        report.ok(f"{db_path.name}: по БД {len(expected)} авторов с суммой > {threshold}")

    fixture_raw = load_json(fixture_path)
    if isinstance(fixture_raw, Exception) or fixture_raw is None:
        report.fail(f"{fixture_path.relative_to(ROOT).as_posix()}: эталон не читается")
        fixture = None
    else:
        fixture = normalize_records(fixture_raw, report, fixture_path.name)
        if fixture:
            report.ok(f"{fixture_path.name}: {len(fixture)} записей")

    if fixture is not None and expected is not None:
        compare_rows(report, f"{fixture_path.name} vs БД", fixture, expected)
        check_sorted(report, fixture_path.name, fixture)

    # результат работы стадии
    if not out_path.exists():
        report.fail(
            f"{out_path.name} не найден — запустите `python main.py --stage {STAGE}` "
            f"(или передайте свой файл через --output)"
        )
        return

    raw = load_json(out_path)
    if isinstance(raw, Exception):
        report.fail(f"{out_path.name}: невалидный JSON ({raw})")
        return
    actual = normalize_records(raw, report, out_path.name)
    if not actual:
        report.fail(f"{out_path.name}: пустой результат")
        return
    report.ok(f"{out_path.name}: {len(actual)} записей")

    check_sorted(report, out_path.name, actual)
    check_threshold(report, out_path.name, actual, threshold)

    if fixture is not None:
        compare_rows(report, f"{out_path.name} vs {fixture_path.name}", actual, fixture)
    if expected is not None:
        compare_rows(report, f"{out_path.name} vs БД", actual, expected)
    if fixture is not None:
        ref_styles = {r["name"]: (norm_tokens(r["types"]), norm_tokens(r["techs"])) for r in fixture}
        soft_styles(report, out_path.name, actual, ref_styles, fixture_path.name)
    if expected:
        soft_styles(report, out_path.name, actual, query_styles(db_path, threshold), db_path.name)


# --------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Чекер задачи export-top-artists")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="файл результата стадии")
    parser.add_argument("--min-total-price", type=float, default=DEFAULT_MIN_TOTAL_PRICE,
                        help="порог суммы коллекции")
    parser.add_argument("--fixture", default=str(ROOT / "tests" / "expensive_artists.json"))
    parser.add_argument("--db", default=str(ROOT / "art_market.db"))
    args = parser.parse_args(argv)

    report = Report()
    files = iter_py_files()

    check_layers(report, files)
    check_conventions(report, files)
    impl = check_task(report, files)
    check_tests_and_docs(report, impl)
    check_data(report, Path(args.output), Path(args.fixture), Path(args.db), args.min_total_price)

    violations = report.violations
    warnings = report.warnings

    print("\n" + "=" * 72)
    for section, _kind, text in warnings:
        print(f"  предупреждение [{section}]: {text}")
    for section, _kind, text in violations:
        print(f"  нарушение [{section}]: {text}")
    print("-" * 72)
    print(f"Предупреждений: {len(warnings)}")
    print(f"нарушений: {len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
