"""Randomized delays imitating human behavior."""
import asyncio
import random
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class HumanLikeThrottle:
    """Manages delays between requests to DeepSeek web chat."""

    def __init__(
        self,
        short_range: Tuple[float, float] = (8.0, 22.0),
        long_range: Tuple[float, float] = (45.0, 75.0),
        batch_size: int = 4,
    ) -> None:
        self.short_range = short_range
        self.long_range = long_range
        self.batch_size = batch_size
        self._counter = 0

    async def wait_before_request(self) -> None:
        self._counter += 1
        if self._counter % self.batch_size == 0:
            delay = random.uniform(*self.long_range)
            logger.info("Long pause %.1fs after %d requests", delay, self._counter)
        else:
            delay = random.uniform(*self.short_range)
            logger.debug("Short pause %.1fs before request #%d", delay, self._counter)
        await asyncio.sleep(delay)

    async def typing_pause(self) -> None:
        delay = random.uniform(1.2, 3.8)
        await asyncio.sleep(delay)

    def reset(self) -> None:
        self._counter = 0
