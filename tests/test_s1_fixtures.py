"""S1 fixture contract: 07:14 / 08:27 BLOCK, 07:59 ALLOW. Verify-only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.replay_fixtures import replay_one
from scripts.s1_gate import first_send_decision, guard_maker_join, guard_still250_send

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "s1"


@pytest.mark.parametrize("case_id", ["0714", "0827", "0759"])
def test_replay_known_windows(case_id: str) -> None:
    ok, line = replay_one(case_id)
    assert ok, line


def test_0714_join_equals_ask_blocks() -> None:
    book = json.loads((FIXTURE_DIR / "0714.json").read_text())["book"]
    assert book["bid_down_250"] == book["ask_down_250"] == 0.57
    assert guard_maker_join(book) == "would_be_taker_blocked"
    assert first_send_decision(book) == ("BLOCK", "would_be_taker_blocked")


def test_0827_cross_ask_blocks() -> None:
    book = json.loads((FIXTURE_DIR / "0827.json").read_text())["book"]
    assert book["bid_up_250"] > book["ask_up_250"]
    assert guard_maker_join(book) == "would_be_taker_blocked"
    assert first_send_decision(book) == ("BLOCK", "would_be_taker_blocked")


def test_0759_maker_both_allows() -> None:
    book = json.loads((FIXTURE_DIR / "0759.json").read_text())["book"]
    assert book["bid_sum"] == 0.69
    assert book["min_bid_size"] == 52
    assert book["bid_up"] < book["ask_up"]
    assert book["bid_down"] < book["ask_down"]
    assert guard_maker_join(book) is None
    assert first_send_decision(book) == ("ALLOW", None)


def test_still250_false_blocks_even_if_maker() -> None:
    book = json.loads((FIXTURE_DIR / "0759.json").read_text())["book"]
    book = {**book, "still_there_250ms": False}
    assert guard_still250_send(book) == "still250_false"
    assert first_send_decision(book) == ("BLOCK", "still250_false")


def test_pair_gt1_refused() -> None:
    book = json.loads((FIXTURE_DIR / "0759.json").read_text())["book"]
    book = {**book, "bid_sum": 1.02, "bid_sum_250": 1.02}
    assert first_send_decision(book) == ("BLOCK", "pair_gt_1_refused")
