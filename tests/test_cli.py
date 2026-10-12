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


def test_cli_parses_export_top_artists_stage() -> None:
    args = build_parser().parse_args(["--stage", "export-top-artists"])
    assert args.stage == "export-top-artists"
    assert args.min_total_price == 3_000_000
    assert args.output == "top_artists.json"

    custom = build_parser().parse_args(
        ["--stage", "export-top-artists", "--min-total-price", "1500000", "--output", "out/top.json"]
    )
    assert custom.min_total_price == 1_500_000
    assert custom.output == "out/top.json"
