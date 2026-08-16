from infra.match.queue_sim_v2 import SCENARIOS, run_queue_v2
from whiskas.l2 import BookTick


def test_scenarios_exist() -> None:
    assert set(SCENARIOS) == {"base", "pessimistic", "optimistic"}
    assert SCENARIOS["base"]["hidden_factor"] == 1.25
    assert SCENARIOS["pessimistic"]["latency_ticks"] == 2
    assert SCENARIOS["optimistic"]["label"] == "upper_bound_only"


def test_queue_does_not_set_size_ok() -> None:
    ticks = [
        BookTick(t=1000 + i, slug="s", asset="btc", tf="5m", t0=1, bu=0.40, bd=0.48, au=0.42, ad=0.50, su=20, sd=20)
        for i in range(5)
    ]
    out = run_queue_v2(ticks=ticks, clip=10, scenario="base")
    assert out["size_ok"] is False
    assert out["go_nogo"] is False
    assert out["n_rest"] >= 1


def test_tape_coarse_band() -> None:
    wins = [{"maker_pair": 0.80, "maker_matched": 50.0, "pair": 0.80, "matched": 50.0}]
    base = run_queue_v2(windows=wins, clip=10, scenario="base")
    opt = run_queue_v2(windows=wins, clip=10, scenario="optimistic")
    assert base["size_ok"] is False
    assert opt["fill_ratio"] >= base["fill_ratio"] - 1e-12
