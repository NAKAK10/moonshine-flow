from moonshine_flow import cli


def test_has_moonshine_backend_true(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "find_spec",
        lambda name: object() if name == "moonshine_voice" else None,
    )
    assert cli._has_moonshine_backend()


def test_has_moonshine_backend_false(monkeypatch) -> None:
    monkeypatch.setattr(cli, "find_spec", lambda name: None)
    assert not cli._has_moonshine_backend()


def test_backend_guidance_has_actionable_text() -> None:
    guidance = cli._backend_guidance()
    assert "uv sync" in guidance
    assert "Moonshine backend package is missing" in guidance


def test_check_permissions_parser_has_request_flag() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["check-permissions", "--request"])
    assert args.request is True
