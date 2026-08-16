from pathlib import Path


def test_nautilus_s1_smoke_is_paper_only() -> None:
    src = Path("scripts/nautilus_s1_smoke.py").read_text()
    assert "No live exec" in src
    assert "create_order" not in src
    assert "exec_client_enabled" in src
    assert "BLOCKED_ON_CATALOG" in src
    assert "LIVE_READY" in src
