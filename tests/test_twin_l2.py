import json
from pathlib import Path

from whiskas.l2 import BookTick, PolicyMaker, action_bucket
from scripts.twin_l2 import run_twin


def test_twin_histogram_on_synthetic_ticks() -> None:
    ticks = [
        BookTick(t=1000 + i, slug="btc-updown-5m-1", asset="btc", tf="5m", t0=1, bu=0.40, bd=0.48, au=0.42, ad=0.50, su=20, sd=20)
        for i in range(3)
    ]
    ticks.append(BookTick(t=1005, slug="btc-updown-5m-1", asset="btc", tf="5m", t0=1, bu=0.50, bd=0.49, au=0.51, ad=0.50, su=20, sd=20))
    out = run_twin(ticks, clip=10, fill="none", regime="pre_2026_08_14_DEBUG")
    assert out["n_ticks"] == 4
    assert out["n_rest"] == 1
    assert out["n_rich"] >= 1
    assert out["size_ok"] is False
    assert out["live_order"] is False
    assert out["pct_bid_sum_le_090"] == 75.0
    assert action_bucket("requote") == "replace"


def test_paper_maker_uses_policy_maker() -> None:
    src = Path("scripts/paper_maker.py").read_text()
    assert "PolicyMaker" in src
    assert "from whiskas.l2 import" in src
