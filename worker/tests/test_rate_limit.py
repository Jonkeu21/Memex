from worker.rate_limit import RateLimiter


def test_under_threshold_no_pause():
    clock = [1000.0]
    rl = RateLimiter(window_seconds=300.0, threshold_ms=10_000, now=lambda: clock[0])
    rl.record(1000)
    rl.record(2000)
    assert rl.total_ms_in_window() == 3000
    assert rl.should_pause() is False
    assert rl.extra_pause_seconds() == 0.0


def test_over_threshold_triggers_pause():
    clock = [1000.0]
    rl = RateLimiter(window_seconds=300.0, threshold_ms=5_000, now=lambda: clock[0])
    rl.record(3000)
    rl.record(3000)
    assert rl.should_pause() is True
    assert rl.extra_pause_seconds() == 75.0  # window/4


def test_old_events_evicted():
    clock = [1000.0]
    rl = RateLimiter(window_seconds=300.0, threshold_ms=5_000, now=lambda: clock[0])
    rl.record(4000)
    clock[0] += 600  # well past window
    rl.record(1000)
    assert rl.total_ms_in_window() == 1000
    assert rl.should_pause() is False


def test_default_now_runs():
    rl = RateLimiter(window_seconds=300.0, threshold_ms=5_000)
    rl.record(100)
    assert rl.total_ms_in_window() == 100
