"""Rate limiter with random jitter for human-like delays."""

import asyncio
import random
import time


class RateLimiter:
    """Rate limiter with configurable delays and random jitter."""

    def __init__(self, min_delay: float = 3.0, max_delay: float = 8.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self._last_action_time: float = 0

    def _random_delay(self) -> float:
        """Generate a random delay between min and max."""
        return random.uniform(self.min_delay, self.max_delay)

    def wait(self) -> float:
        """Wait for a random delay. Returns the actual wait time."""
        delay = self._random_delay()
        elapsed = time.time() - self._last_action_time
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_action_time = time.time()
        return delay

    async def async_wait(self) -> float:
        """Async version of wait."""
        delay = self._random_delay()
        elapsed = time.time() - self._last_action_time
        remaining = delay - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_action_time = time.time()
        return delay

    def reset(self) -> None:
        """Reset the last action time."""
        self._last_action_time = 0
