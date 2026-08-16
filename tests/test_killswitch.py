from whiskas.killswitch import evaluate_kill, rolling_win_rate


def test_rolling_wr_none_until_50() -> None:
    assert rolling_win_rate([True] * 49) is None
    assert rolling_win_rate([True] * 50) == 1.0


def test_kill_on_bad_wr() -> None:
    wins = [False] * 30 + [True] * 20
    d = evaluate_kill(wins, day_pnl=1.0, start_equity=100.0)
    assert d.halt
    assert "wr" in d.reason


def test_kill_on_day_dd() -> None:
    wins = [True] * 50
    d = evaluate_kill(wins, day_pnl=-9.0, start_equity=100.0)
    assert d.halt
    assert "day_pnl" in d.reason


def test_ok_when_healthy() -> None:
    wins = [True] * 40 + [False] * 10
    d = evaluate_kill(wins, day_pnl=-2.0, start_equity=100.0)
    assert not d.halt
