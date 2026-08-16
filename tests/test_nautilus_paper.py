from pathlib import Path

from infra.nautilus.paper_engine import NautilusPaperEngine, booktick_to_quotes, probe_nautilus
from whiskas.l2 import BookTick


def test_probe_and_no_live_import() -> None:
    p = probe_nautilus()
    assert p["historical_l2"] is False
    assert p["live"] is False
    src = Path("infra/nautilus/paper_engine.py").read_text()
    assert "import nautilus_trader.adapters.polymarket" not in src
    assert "create_order" not in src
    assert "Does NOT import adapters.polymarket" in src


def test_booktick_to_quotes_and_engine() -> None:
    if not probe_nautilus().get("installed"):
        return
    tick = BookTick(
        t=1786900000,
        slug="btc-updown-5m-1",
        asset="btc",
        tf="5m",
        t0=1,
        bu=0.40,
        bd=0.48,
        au=0.42,
        ad=0.50,
        su=12,
        sd=15,
        sau=12,
        sad=15,
    )
    quotes = booktick_to_quotes(tick)
    assert len(quotes) == 2
    assert str(quotes[0].instrument_id).endswith(".PAPER")
    out = NautilusPaperEngine().run([tick, tick])
    assert out["live_orders"] is False
    assert out["size_ok"] is False
    assert out["g5_g6_unlocked"] is False
    assert out["n_quotes"] == 4
    assert out["n_rest"] >= 1
    assert not Path("configs/generated/LIVE_READY.yaml").is_file()
    assert not Path("data/ops/G5_size_ok.flag").is_file()
    assert not Path("data/ops/G6_fill_calibrated.flag").is_file()
