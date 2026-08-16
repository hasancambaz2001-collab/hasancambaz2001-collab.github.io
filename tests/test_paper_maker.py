import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paper_maker import (
    CANCEL_ABOVE,
    CANCEL_RICH,
    CLIP_DEFAULT,
    MAKER_ASSETS,
    MAKER_TFS,
    PAIR_MAX,
    REQUOTE_MAX,
    REST_MAX,
    decide_maker,
    level_eaten,
    load_maker_yaml,
    snapshot_maker,
)


def test_rest_both_when_cheap_and_deep() -> None:
    rec, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=12,
        bid_sz_down=15,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    assert rec["reason"] == "rest"
    assert rec["rest"] is True
    assert rec["live_order"] is False
    assert rec["bid_sum"] is not None and abs(rec["bid_sum"] - 0.88) < 1e-12
    assert rec["bid_sum"] <= REST_MAX
    assert len(rec["orders"]) == 2
    assert all(o["type"] == "GTC" and o["side"] == "BUY" and o["size"] == 10 for o in rec["orders"])
    assert state is not None and state["px_up"] == 0.40


def test_rich_bid_sum_no_rest() -> None:
    rec, state = decide_maker(
        bid_up=0.50,
        bid_down=0.49,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.51,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    assert rec["reason"] == "rich_bid_sum"
    assert rec["rest"] is False
    assert rec["orders"] == []
    assert state is None
    assert rec["live_order"] is False


def test_thin_bid_no_rest() -> None:
    rec, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=9,
        bid_sz_down=40,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    assert rec["reason"] == "thin_bid"
    assert rec["rest"] is False
    assert state is None


def test_rich_cancel_when_bid_sum_gt_092() -> None:
    rest, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    assert rest["reason"] == "rest"
    rec, new_state = decide_maker(
        bid_up=0.47,
        bid_down=0.46,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.48,
        ask_down=0.47,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
    )
    assert rec["bid_sum"] is not None and rec["bid_sum"] > CANCEL_RICH
    assert rec["reason"] == "rich_cancel"
    assert rec["cancel"] is True
    assert new_state is None
    assert rec["live_order"] is False


def test_cancel_age_over_45s() -> None:
    _, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    rec, new_state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=state,
        now=1046.0,
        t0=1,
        clip=10,
    )
    assert rec["reason"] == "cancel_age"
    assert rec["cancel"] is True
    assert new_state is None


def test_one_leg_eaten_complete_if_pair_le_090() -> None:
    _, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    rec, new_state = decide_maker(
        bid_up=0.38,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.39,
        ask_down=0.49,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
    )
    assert rec["eaten_up"] is True
    assert rec["eaten_down"] is False
    assert rec["complete"] is True
    assert rec["reason"] == "complete"
    assert rec["fill_px"] == 0.40
    assert rec["opp_ask"] == 0.49
    assert rec["complete_pair"] is not None and abs(rec["complete_pair"] - 0.89) < 1e-12
    assert rec["orders"][0]["outcome"] == "Down"
    assert rec["orders"][0]["type"] == "FOK"
    assert rec["live_order"] is False
    assert new_state is None


def test_one_leg_eaten_rich_complete_cancels_leftover() -> None:
    _, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    rec, new_state = decide_maker(
        bid_up=0.38,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.39,
        ask_down=0.55,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
    )
    assert rec["eaten_up"] is True
    assert rec["complete"] is False
    assert rec["cancel"] is True
    assert rec["reason"] == "rich_complete"
    assert rec["complete_pair"] is not None and rec["complete_pair"] > REST_MAX
    assert rec["orders"] == []
    assert rec["live_order"] is False
    assert new_state is None


def test_never_complete_pair_gt_1() -> None:
    _, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    rec, new_state = decide_maker(
        bid_up=0.38,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.39,
        ask_down=0.70,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
    )
    assert rec["complete"] is False
    assert rec["pair_gt_1"] is False
    assert rec["reason"] in {"rich_complete", "pair_gt_1"}
    assert rec["live_order"] is False
    assert new_state is None


def test_requote_joins_new_best() -> None:
    _, state = decide_maker(
        bid_up=0.40,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.42,
        ask_down=0.50,
        state=None,
        now=1000.0,
        t0=1,
        clip=10,
    )
    rec, new_state = decide_maker(
        bid_up=0.41,
        bid_down=0.48,
        bid_sz_up=20,
        bid_sz_down=20,
        ask_up=0.43,
        ask_down=0.50,
        state=state,
        now=1002.0,
        t0=1,
        clip=10,
    )
    assert rec["reason"] == "requote"
    assert rec["requote"] is True
    assert rec["rest"] is True
    assert new_state is not None
    assert new_state["px_up"] == 0.41
    assert new_state["rest_ts"] == 1002.0


def test_level_eaten_and_snapshot_no_live() -> None:
    assert level_eaten(0.40, 0.38, 0.42) is True
    assert level_eaten(0.40, 0.40, 0.42) is False
    assert level_eaten(0.40, 0.40, 0.40) is True
    tokens = {"Up": "u", "Down": "d"}
    books = {
        "Up": {"bids": [{"price": "0.40", "size": "12"}], "asks": [{"price": "0.42", "size": "12"}]},
        "Down": {"bids": [{"price": "0.48", "size": "12"}], "asks": [{"price": "0.50", "size": "12"}]},
    }
    rec, state = snapshot_maker(asset="doge", tf="15m", tokens=tokens, books=books, now=1786886400)
    assert rec["asset"] == "doge"
    assert rec["tf"] == "15m"
    assert rec["reason"] == "rest"
    assert rec["live_order"] is False
    assert rec["book"] == "maker"
    assert rec["still_there_250ms"] is True
    assert rec["skip_reason"] is None
    assert rec["bid_sum"] is not None
    assert state is not None
    src = Path("scripts/paper_maker.py").read_text(encoding="utf-8")
    assert "create_order" not in src
    assert "post_order" not in src
    assert "data/paper/intended.jsonl" in src
    assert CLIP_DEFAULT == 10.0
    assert PAIR_MAX == 0.90
    assert CANCEL_ABOVE == 0.92
    assert REQUOTE_MAX == 2.0
    assert REST_MAX == PAIR_MAX
    assert CANCEL_RICH == CANCEL_ABOVE
    assert MAKER_ASSETS == ("btc", "eth", "sol", "xrp", "doge")
    assert MAKER_TFS == ("5m", "15m")
    assert "4h" not in MAKER_TFS
    cfg = load_maker_yaml()
    assert Path(cfg["path"]).name == "PAPER_ONLY.yaml"
    assert cfg["pair_max"] == 0.90
    assert cfg["cancel_above"] == 0.92
    assert cfg["clip"] == 10.0
    assert cfg["requote"] <= 1.0
    assert cfg["interval"] <= 1.0
    assert cfg["assets"] == MAKER_ASSETS
    assert cfg["tfs"] == MAKER_TFS
    assert cfg["live_order"] is False
    yaml = Path("configs/maker.yaml").read_text(encoding="utf-8")
    assert "pair_max: 0.90" in yaml
    assert "cancel_above: 0.92" in yaml
    assert "requote: 2" in yaml
