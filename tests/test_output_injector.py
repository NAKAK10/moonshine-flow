from moonshine_flow.output_injector import OutputInjector


def test_parse_shortcut() -> None:
    key, modifiers = OutputInjector._parse_shortcut("cmd+shift+v")

    assert key == "v"
    assert modifiers == ["command down", "shift down"]
