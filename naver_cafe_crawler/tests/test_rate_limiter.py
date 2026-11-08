import pytest

from crawler.types import BlockedError, TransientError
from utils.rate_limiter import RateLimiter, with_retry


def test_rate_limiter_enforces_gap():
    t = [0.0]
    sleeps = []
    rl = RateLimiter(3, 3, sleep=lambda s: (sleeps.append(s), t.__setitem__(0, t[0] + s)),
                     clock=lambda: t[0])
    rl.wait()           # 첫 요청 대기 없음
    t[0] += 1.0
    rl.wait()           # 1초 경과 → 2초 추가 대기
    assert sleeps == [pytest.approx(2.0)]


def test_retry_only_transient():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("x")
        return "ok"
    waits = []
    assert with_retry(flaky, 2, 5, sleep=waits.append) == "ok"
    assert waits == [5, 10]  # 지수 백오프

    def blocked():
        raise BlockedError("429")
    with pytest.raises(BlockedError):
        with_retry(blocked, 3, 1, sleep=lambda s: None)
