"""Human-like pacing between actions: a random delay with jitter, declared once here."""

import random
import time

MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 8.0


class RateLimiter:
    def __init__(self, min_delay: float = MIN_DELAY_SECONDS, max_delay: float = MAX_DELAY_SECONDS):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_action_time: float = 0

    def wait(self) -> float:
        """Sleep so that at least a random delay has passed since the last action. Returns the delay."""
        delay = random.uniform(self.min_delay, self.max_delay)
        remaining = delay - (time.time() - self._last_action_time)
        if remaining > 0:
            time.sleep(remaining)
        self._last_action_time = time.time()
        return delay

    def reset(self) -> None:
        self._last_action_time = 0
