from pathlib import Path

from whiskas.live_config import (
    evaluate_gates,
    live_status,
    load_activity,
    paper_only_payload,
)


def test_g5_g6_fail_without_flags(tmp_path: Path) -> None:
    ev = evaluate_gates(
        bosona_cover=0.802,
        mo_cover=0.847,
        pair_gt_1_trade=False,
        shadow_only=True,
        g5_flag=tmp_path / "G5_size_ok.flag",
        g6_flag=tmp_path / "G6_fill_calibrated.flag",
    )
    assert ev["gates"]["G1_bosona_cover"]["pass"] is True
    assert ev["gates"]["G2_mo_cover"]["pass"] is True
    assert ev["gates"]["G3_pair_gt1_trade"]["pass"] is True
    assert ev["gates"]["G4_shadow_path"]["pass"] is True
    assert ev["gates"]["G5_size_ok"]["pass"] is False
    assert ev["gates"]["G6_fill_calibration"]["pass"] is False
    assert ev["gates"]["G7_accept_risk"]["pass"] is False
    assert ev["live_blocked"] is True
    assert live_status(eval_gates=ev, accept_risk=True) == "LIVE_BLOCKED"
    assert live_status(eval_gates=ev, accept_risk=False) == "LIVE_BLOCKED"


def test_live_ready_only_with_flags_and_accept(tmp_path: Path) -> None:
    g5 = tmp_path / "G5_size_ok.flag"
    g6 = tmp_path / "G6_fill_calibrated.flag"
    g5.write_text("")
    g6.write_text("")
    ev = evaluate_gates(
        bosona_cover=0.80,
        mo_cover=0.80,
        pair_gt_1_trade=False,
        shadow_only=True,
        g5_flag=g5,
        g6_flag=g6,
        accept_risk=True,
    )
    assert ev["g5_g6"] is True
    assert ev["gates"]["G7_accept_risk"]["pass"] is True
    assert live_status(eval_gates=ev, accept_risk=False) == "LIVE_BLOCKED"
    assert live_status(eval_gates=ev, accept_risk=True) == "LIVE_READY"


def test_load_activity_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "tape.jsonl"
    p.write_text('{"type":"TRADE","n":1}\n{"type":"TRADE","n":2}\n')
    rows = load_activity(p)
    assert len(rows) == 2
    assert rows[1]["n"] == 2


def test_paper_only_locks() -> None:
    p = paper_only_payload()
    assert p["live_orders"] is False
    assert p["clip"] == 10
    assert p["pair_max"] == 0.90
    assert p["assets"] == ["btc", "eth", "sol", "xrp", "doge"]
    assert p["smart_copy"]["shadow_only"] is True
    assert p["pair_gt_1_trade"] is False
    assert p["size_ok"] is False
    src = Path("scripts/produce_live_config.py").read_text()
    assert "--i-accept-risk" in src
    assert "LIVE_BLOCKED" in src
    assert "LIVE_GATE_REPORT.md" in src
    assert "sk-" not in Path("whiskas/live_config.py").read_text()
