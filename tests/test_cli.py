from erarta_scraper.cli import build_parser, settings_from_args


def test_cli_parses_stage_and_limits() -> None:
    args = build_parser().parse_args(["--stage", "visit", "--limit", "50", "--pages", "3", "--headless"])
    assert args.stage == "visit"
    assert args.limit == 50
    assert args.pages == 3
    assert args.headless is True
    settings = settings_from_args(args)
    assert settings.pages_count == 3
    assert settings.headless is True


def test_cli_parses_retry_failed_defaults_and_overrides() -> None:
    args = build_parser().parse_args(["--stage", "retry-failed"])
    assert args.stage == "retry-failed"
    assert args.max_retries is None
    assert args.report_file is None
    settings = settings_from_args(args)
    assert settings.max_retries == 20
    assert settings.report_file == "retry_report.csv"

    args = build_parser().parse_args(["--max-retries", "5", "--report-file", "out.csv"])
    settings = settings_from_args(args)
    assert settings.max_retries == 5
    assert settings.report_file == "out.csv"
