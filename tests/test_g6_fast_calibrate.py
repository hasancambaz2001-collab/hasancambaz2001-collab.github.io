from pathlib import Path

from scripts.g6_fast_calibrate import (
    N_REST_MIN,
    edge_proxy,
    evaluate_pass,
    one_leg_stats,
    policy_rests,
    run_g6_fast,
    ticks_from_joined_bbo,
)
from whiskas.l2 import BookTick
import pandas as pd


def _tick(slug: str, t: float, *, bu=0.40, bd=0.48, su=20.0, sd=20.0, t0: int | None = None) -> BookTick:
    return BookTick(
        t=t,
        slug=slug,
        asset="btc",
        tf="5m",
        t0=int(t0 if t0 is not None else t),
        bu=bu,
        bd=bd,
        au=0.42,
        ad=0.50,
        su=su,
        sd=sd,
    )


def test_one_leg_skips_pair_edge() -> None:
    slim = pd.DataFrame({"best_bid": [0.40, 0.41], "best_ask": [0.42, 0.43]})
    stats = one_leg_stats(slim, "btc-updown-5m-1")
    assert stats["pair_edge"] == "skipped_one_leg"
    assert stats["n_ticks"] == 2


def test_joined_yes_plus_dump_down_can_rest() -> None:
    slim = pd.DataFrame(
        {
            "timestamp": [1000.0, 1001.0],
            "best_bid": [0.40, 0.40],
            "best_ask": [0.42, 0.42],
            "bid_size": [20.0, 20.0],
        }
    )
    ticks = ticks_from_joined_bbo(
        slim, slug="btc-updown-5m-1", asset="btc", tf="5m", t0=1, down_px=0.48, down_sz=20.0
    )
    assert ticks[0].bd == 0.48
    assert ticks[0].bid_sum is not None and ticks[0].bid_sum <= 0.90
    rests = policy_rests(ticks, clip=10, pair_max=0.90)
    assert len(rests) == 1
    assert rests[0]["reason"] == "rest"
    assert rests[0]["pair_gt_1"] is False


def test_fail_does_not_write_flag(tmp_path: Path) -> None:
    ticks = [_tick("only-one", 1000.0, t0=1)]
    stats = run_g6_fast(
        clip=10,
        pair_max=0.90,
        download=False,
        extra_ticks=ticks,
        root=tmp_path,
        write_outputs=True,
    )
    assert stats["n_rest"] < N_REST_MIN
    assert stats["g6_pass"] is False
    assert stats["g6_flag_written"] is False
    assert not (tmp_path / "data" / "ops" / "G6_fill_calibrated.flag").is_file()
    assert (tmp_path / "data" / "reports" / "G6_FAST.md").is_file()
    assert "n_rest" in (tmp_path / "data" / "reports" / "G6_FAST.md").read_text()


def test_pass_writes_flag_not_live_ready(tmp_path: Path) -> None:
    ticks = [_tick(f"s{i}", 1000.0 + i, t0=i, bu=0.40, bd=0.48) for i in range(N_REST_MIN)]
    stats = run_g6_fast(
        clip=10,
        pair_max=0.90,
        download=False,
        extra_ticks=ticks,
        root=tmp_path,
        write_outputs=True,
    )
    assert stats["n_rest"] >= N_REST_MIN
    assert stats["edge_proxy_fee0"] >= 0
    assert stats["g6_pass"] is True
    assert (tmp_path / "data" / "ops" / "G6_fill_calibrated.flag").is_file()
    assert not (tmp_path / "configs" / "generated" / "LIVE_READY.yaml").is_file()
    assert not (tmp_path / "data" / "ops" / "G5_size_ok.flag").is_file()
    assert stats["pair_gt_1_trade"] is False


def test_edge_proxy_ignores_pair_gt_1() -> None:
    rests = [
        {"bid_sum": 0.88, "bid_up": 0.40, "bid_down": 0.48, "t": 1786900000},
        {"bid_sum": 1.02, "bid_up": 0.51, "bid_down": 0.51, "t": 1786900000},
    ]
    out = edge_proxy(rests, clip=10)
    assert out["edge_proxy_fee0"] == 10 * (1 - 0.88)
    passed, reasons = evaluate_pass(
        {"n_rest": 50, "edge_proxy_fee0": out["edge_proxy_fee0"], "report_written": True, "pair_gt_1_trade": False}
    )
    assert passed is True
    assert reasons == []


def test_src_locks() -> None:
    src = Path("scripts/g6_fast_calibrate.py").read_text(encoding="utf-8")
    assert "LIVE_READY" in src
    assert "pair_gt_1_trade" in src
    assert "create_order" not in src
    assert "Never complement" in src
    assert "--download" in src
