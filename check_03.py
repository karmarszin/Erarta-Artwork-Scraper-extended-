#!/usr/bin/env python3
"""check_03.py — статический чекер конвенций проекта Erarta ETL.

Что проверяется:
  1. Нарушения слоёв (README «Слои» + AGENTS.md): матрица импортов между
     слоями, утечки сторонних библиотек (selenium/sqlalchemy), импорт cli
     только из main.py, сырой SQL в pipeline/ и в cli.py.
  2. Конвенции (README «Конвенции» + AGENTS.md): нет print в библиотечном
     коде, env-префикс ERARTA_, локаторы By.XPATH/CSS только в scraping/,
     единственный логгер `erarta` (включая getLogger() без имени).
  3. Структурные конвенции (README №1-3, №5, №9; AGENTS #9-10): иерархия
     ошибок, кэш+flush в get_or_create_id, идемпотентный enqueue и статусы
     очереди (скоуп — db/repositories.py), Pace в BrowserSession, __all__
     в суб-пакетах, статические литералы default в argparse.
     Осознанно вне чекера (остаётся Варианту 2, LLM + ручная сверка):
     №4 батч-коммит, условная фикстура выгрузки, алиасы as db/session,
     порядок cache→flush. Note для REPORT: default=Name (модульная
     константа) в add_argument тоже считается нарушением — разрешены
     только литералы (AGENTS #10 «статические литералы»).

Итог: «нарушений: N» + список файлов/строк. Код выхода 1, если N > 0.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:  # Windows console в cp1251
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv", "node_modules", ".idea", ".vscode"}


# отчёт
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


# файлы
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


# 1. Слои
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
    "analytics": "analytics.py (сервис)",
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


SQL_PATTERNS = re.compile(
    r"\bselect\s*\(|func\.sum\s*\(|\.group_by\s*\(|\bhaving\s*\(|session\.execute\s*\("
)


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
        # сырой SQL/агрегации в pipeline/ запрещены (AGENTS.md «Сырой SQL в Pipeline»)
        if r.startswith("erarta_scraper/pipeline/") and r.endswith(".py"):
            sql_lines = [
                i for i, line in enumerate(read_text(path).splitlines(), 1)
                if SQL_PATTERNS.search(line)
            ]
            if sql_lines:
                problems += 1
                report.fail(
                    f"{r}: сырой SQL/агрегация в слое pipeline (строки {', '.join(map(str, sql_lines))}; "
                    f"AGENTS.md «Сырой SQL в Pipeline», README: db = repositories)"
                )
        # сырой SQL в cli запрещён (AGENTS.md «SQL в CLI», README: cli = аргументы/логирование/запуск)
        if r == "erarta_scraper/cli.py":
            sql_lines = [
                i for i, line in enumerate(read_text(path).splitlines(), 1)
                if SQL_PATTERNS.search(line)
            ]
            if sql_lines:
                problems += 1
                report.fail(
                    f"{r}: SQL/агрегация в слое CLI (строки {', '.join(map(str, sql_lines))}; "
                    f"AGENTS.md «SQL в CLI»)"
                )
    if problems == 0:
        report.ok("нарушений слоёв не найдено")


# 2. Конвенции README
def _is_environ(node: ast.AST) -> bool:
    """True для os.environ."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def environ_key(node: ast.AST) -> str | None:
    """Имя переменной окружения из os.getenv("X") / os.environ.get("X") / os.environ["X"]."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "getenv":
            pass
        elif isinstance(func, ast.Attribute) and (
            (func.attr == "get" and _is_environ(func.value)) or (func.attr == "getenv" and isinstance(func.value, ast.Name) and func.value.id == "os")
        ):
            pass
        else:
            return None
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value
        return None
    if isinstance(node, ast.Subscript) and _is_environ(node.value):
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
    return None


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

        # №7: конфиг из env с префиксом ERARTA_* (getenv / os.environ.get / os.environ[...])
        for node in ast.walk(tree):
            name = environ_key(node)
            if name is not None and not name.startswith("ERARTA_"):
                problems += 1
                report.fail(f"{r}:{getattr(node, 'lineno', '?')} — env-переменная `{name}` без префикса ERARTA_ (конвенция №7)")

        # №6: XPath/CSS-локаторы живут в scraping/
        if re.search(r"By\.(XPATH|CSS_SELECTOR)", src) and not r.startswith("erarta_scraper/scraping/"):
            for i, line in enumerate(src.splitlines(), 1):
                if re.search(r"By\.(XPATH|CSS_SELECTOR)", line):
                    problems += 1
                    report.fail(f"{r}:{i} — локатор вне scraping/ (конвенция №6)")

        # №8: логгер один — `erarta`
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getLogger"
            ):
                continue
            if not node.args:
                problems += 1
                report.fail(
                    f"{r}:{node.lineno} — getLogger() без имени возвращает root-логгер вместо `erarta` (конвенция №8)"
                )
            elif (
                isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value != "erarta"
            ):
                problems += 1
                report.fail(f"{r}:{node.lineno} — логгер `{node.args[0].value}` вместо `erarta` (конвенция №8)")

    if problems == 0:
        report.ok("нарушений конвенций не найдено")


# 3. Структурные конвенции (README №1-3, №5, №9; AGENTS #9-10)
def _find_def(tree: ast.AST, name: str):
    """Последнее определение функции/метода с данным именем."""
    found = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            found = node
    return found


def _attr_chain(node: ast.AST) -> list[str]:
    """Имена в цепочке атрибутов: self.pace.wait -> ['wait', 'pace', 'self']."""
    names: list[str] = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        names.append(node.id)
    return names


def _enum_member_ref(node: ast.AST, member: str) -> bool:
    """ArtworkStatus.<member> (в т.ч. в цепочке .value)."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == member
        and isinstance(node.value, ast.Name)
        and node.value.id == "ArtworkStatus"
    )


def check_structural(report: Report, files: list[Path]) -> None:
    report.section("3. Структурные конвенции (README №1-3, №5, №9; AGENTS #9-10)")
    problems = 0

    def fail(text: str) -> None:
        nonlocal problems
        problems += 1
        report.fail(text)

    # №9: Pace в BrowserSession (README: пауза между запросами)
    browser = ROOT / "erarta_scraper/scraping/browser.py"
    if browser.exists():
        tree = parse_tree(browser, report)
        if tree is not None:
            has_pace = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "Pace"
                for node in ast.walk(tree)
            )
            has_wait = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "wait"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr == "pace"
                for node in ast.walk(tree)
            )
            if not (has_pace and has_wait):
                fail(
                    "erarta_scraper/scraping/browser.py: нет Pace(...) или pace.wait() "
                    "(конвенция README №9, «Pace в BrowserSession.get»)"
                )

    # AGENTS #10: default= в add_argument — только статический литерал
    # (Name/Call запрещены осознанно: «статические литералы», см. докстринг).
    # Скоуп — файлы проекта (как в §1): пакет + точки входа; check.py и
    # прочие скрипты лабы не сканируются.
    entrypoints = {"main.py", "models.py", "link_scraper.py", "link_visitor.py"}
    for path in files:
        r = rel(path)
        if not (r.startswith("erarta_scraper/") or r in entrypoints):
            continue
        tree = parse_tree(path, report)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                continue
            for kw in node.keywords:
                if kw.arg == "default" and not isinstance(kw.value, ast.Constant):
                    fail(
                        f"{r}:{node.lineno} — default= не статический литерал "
                        f"(AGENTS.md «Совместимость дефолтов CLI»; разрешены только "
                        f"None/числа/строки/bool — default=Name тоже запрещён)"
                    )

    # №5: иерархия ошибок (README; только 4 обязательных класса)
    exc_path = ROOT / "erarta_scraper/exceptions.py"
    if exc_path.exists():
        tree = parse_tree(exc_path, report)
        if tree is not None:
            expected = {
                "ScraperError": "Exception",
                "ParseError": "ScraperError",
                "BrowserError": "ScraperError",
                "QueueError": "ScraperError",
            }
            bases_by_class: dict[str, list[str]] = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases: list[str] = []
                    for base in node.bases:
                        bases.extend(_attr_chain(base))
                    bases_by_class[node.name] = bases
            for cls, want in expected.items():
                got = bases_by_class.get(cls)
                if got is None:
                    fail(f"erarta_scraper/exceptions.py: нет класса {cls} (конвенция README №5)")
                elif want not in got:
                    fail(
                        f"erarta_scraper/exceptions.py: {cls} наследует "
                        f"{', '.join(got) or '—'}, а не {want} (конвенция README №5)"
                    )

    # AGENTS #9: __all__ в суб-пакетах (корневой __init__ без импортов — пропускаем)
    for path in files:
        r = rel(path)
        if not r.startswith("erarta_scraper/") or not r.endswith("__init__.py"):
            continue
        if r == "erarta_scraper/__init__.py":
            continue
        tree = parse_tree(path, report)
        if tree is None:
            continue
        imported: set[str] = set()
        star = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        star = True
                        continue
                    name = alias.asname or alias.name
                    if not name.startswith("_"):
                        imported.add(name)
            # ast.Import (import logging) — модульные импорты в __all__ не входят
        if star or not imported:
            continue
        exported: set[str] = set()
        has_all = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                has_all = True
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    exported.update(
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    )
        if not has_all:
            fail(
                f"{r}: есть импорты, но нет __all__ "
                f"(AGENTS.md «Синхронизация публичного API пакетов»)"
            )
        else:
            missing = imported - exported
            if missing:
                fail(
                    f"{r}: в __all__ не входят импортированные имена {sorted(missing)} "
                    f"(AGENTS.md «Синхронизация публичного API пакетов»)"
                )

    # README №1-3: очередь, кэш, идемпотентность — скоуп db/repositories.py
    repo_path = ROOT / "erarta_scraper/db/repositories.py"
    if repo_path.exists():
        tree = parse_tree(repo_path, report)
        if tree is not None:
            # №3: get-or-create с кэшем и flush (presence, порядок не проверяется)
            func = _find_def(tree, "get_or_create_id")
            if func is None:
                fail("erarta_scraper/db/repositories.py: нет метода get_or_create_id (конвенция README №3)")
            else:
                has_cache = any(
                    isinstance(n, ast.Attribute) and n.attr == "_cache" for n in ast.walk(func)
                )
                has_flush = any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "flush"
                    for n in ast.walk(func)
                )
                if not (has_cache and has_flush):
                    fail(
                        "erarta_scraper/db/repositories.py: get_or_create_id без кэша "
                        "_cache и/или flush() (конвенция README №3)"
                    )

            # №1: статусы очереди через ArtworkStatus (по API-именам методов)
            for fname, member in [("enqueue_urls", "PENDING"), ("mark_done", "DONE"), ("mark_error", "ERROR")]:
                fn = _find_def(tree, fname)
                if fn is None:
                    fail(
                        f"erarta_scraper/db/repositories.py: нет метода {fname} "
                        f"(конвенция README №1, очередь в БД)"
                    )
                elif not any(_enum_member_ref(n, member) for n in ast.walk(fn)):
                    fail(
                        f"erarta_scraper/db/repositories.py: {fname} не использует "
                        f"ArtworkStatus.{member} (конвенция README №1)"
                    )

            # №2: идемпотентный enqueue (метод SQLAlchemy или raw-SQL — оба законны в db/)
            enq = _find_def(tree, "enqueue_urls")
            if enq is not None:
                has_method = any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "on_conflict_do_nothing"
                    for n in ast.walk(enq)
                )
                has_sql = any(
                    isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and ("on conflict" in n.value.lower() or "or ignore" in n.value.lower())
                    for n in ast.walk(enq)
                )
                if not (has_method or has_sql):
                    fail(
                        "erarta_scraper/db/repositories.py: enqueue_urls без ON CONFLICT "
                        "DO NOTHING (конвенция README №2, идемпотентный enqueue)"
                    )

            # №1: сырые строки-статусы вместо enum — только в repositories.py
            for node in ast.walk(tree):
                offender = None
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                    and any(
                        isinstance(t, ast.Attribute) and t.attr == "status"
                        for t in node.targets
                    )
                ):
                    offender = node
                elif isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "status"
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                        ):
                            offender = node
                elif isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if (
                            kw.arg == "status"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                        ):
                            offender = node
                if offender is not None:
                    fail(
                        f"erarta_scraper/db/repositories.py:{offender.lineno} — сырая "
                        f"строка вместо ArtworkStatus (конвенция README №1)"
                    )

    if problems == 0:
        report.ok("структурных нарушений не найдено")


def main() -> int:
    report = Report()
    files = iter_py_files()

    check_layers(report, files)
    check_conventions(report, files)
    check_structural(report, files)

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
