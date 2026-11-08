"""요청 간격 제어와 제한 재시도."""
from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

from crawler.types import TransientError
from utils.logger import get_logger

T = TypeVar("T")
log = get_logger("rate")


class RateLimiter:
    """직전 요청 이후 최소 delay_min~delay_max 초(무작위) 간격을 보장. 동시 요청 1건(순차 처리)."""

    def __init__(self, delay_min: float, delay_max: float,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.delay_min = delay_min
        self.delay_max = max(delay_min, delay_max)
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def wait(self) -> float:
        waited = 0.0
        if self._last is not None:
            target = random.uniform(self.delay_min, self.delay_max)
            elapsed = self._clock() - self._last
            if elapsed < target:
                waited = target - elapsed
                self._sleep(waited)
        self._last = self._clock()
        return waited

    def penalty(self, seconds: float) -> None:
        """오류 발생 시 추가 대기."""
        self._sleep(seconds)
        self._last = self._clock()


def with_retry(fn: Callable[[], T], max_retries: int, backoff_seconds: float,
               sleep: Callable[[float], None] = time.sleep) -> T:
    """TransientError 만 재시도(지수 백오프). 차단/CAPTCHA 등은 즉시 전파."""
    attempt = 0
    while True:
        try:
            return fn()
        except TransientError as exc:
            if attempt >= max_retries:
                raise
            wait = backoff_seconds * (2 ** attempt)
            attempt += 1
            log.warning("일시 오류(%s). %.0f초 후 재시도 %d/%d", exc, wait, attempt, max_retries)
            sleep(wait)
