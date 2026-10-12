from erarta_scraper.cli import build_parser, main, settings_from_args


def test_cli_parses_stage_and_limits() -> None:
    args = build_parser().parse_args(["--stage", "visit", "--limit", "50", "--pages", "3", "--headless"])
    assert args.stage == "visit"
    assert args.limit == 50
    assert args.pages == 3
    assert args.headless is True
    settings = settings_from_args(args)
    assert settings.pages_count == 3
    assert settings.headless is True


def test_cli_parses_export_top_artists_defaults() -> None:
    args = build_parser().parse_args(["--stage", "export-top-artists"])
    assert args.stage == "export-top-artists"
    assert args.min_total_price == 3_000_000
    assert args.output == "top_artists.json"


def test_cli_parses_export_top_artists_options() -> None:
    args = build_parser().parse_args(
        ["--stage", "export-top-artists", "--min-total-price", "500000", "--output", "rich.json"]
    )
    assert args.min_total_price == 500000
    assert args.output == "rich.json"


def test_cli_export_top_artists_end_to_end(tmp_path) -> None:
    db_path = tmp_path / "db.sqlite"
    output = tmp_path / "top_artists.json"
    exit_code = main(
        [
            "--stage",
            "export-top-artists",
            "--db-path",
            str(db_path),
            "--output",
            str(output),
        ]
    )
    assert exit_code == 0
    assert output.exists()
