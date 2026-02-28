from benchmarks.server.routes.runs import _format_json_for_display


def test_format_json_for_display_keeps_unicode_characters() -> None:
    rendered = _format_json_for_display({"synonym": "快乐"})

    assert "快乐" in rendered
    assert "\\u5feb\\u4e50" not in rendered
