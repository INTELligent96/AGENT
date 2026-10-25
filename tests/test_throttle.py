"""Tests for throttling and Mock provider."""
import asyncio
import pytest
from utils.throttle import HumanLikeThrottle


@pytest.mark.asyncio
async def test_throttle_short_range(monkeypatch):
    delays = []
    real_sleep = asyncio.sleep  # сохранили оригинал ДО подмены

    def fake_sleep(d):
        delays.append(d)
        return real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    t = HumanLikeThrottle(short_range=(8.0, 22.0), batch_size=100)
    for _ in range(3):
        await t.wait_before_request()

    assert len(delays) == 3, "Expected 3 delays, got %d" % len(delays)
    for d in delays:
        assert 8.0 <= d <= 22.0, "Delay %s out of range" % d


@pytest.mark.asyncio
async def test_throttle_long_pause_after_batch(monkeypatch):
    delays = []
    real_sleep = asyncio.sleep

    def fake_sleep(d):
        delays.append(d)
        return real_sleep(0)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)

    t = HumanLikeThrottle(
        short_range=(8.0, 22.0),
        long_range=(45.0, 75.0),
        batch_size=4,
    )
    for _ in range(4):
        await t.wait_before_request()

    assert len(delays) == 4, "Expected 4 delays, got %d" % len(delays)
    # Первые три — короткие
    for d in delays[:3]:
        assert 8.0 <= d <= 22.0
    # Четвёртая — длинная
    assert 45.0 <= delays[-1] <= 75.0


@pytest.mark.asyncio
async def test_mock_provider_uses_throttle():
    from providers.deepseek_web import MockProvider
    p = MockProvider()
    p.throttle = HumanLikeThrottle(
        short_range=(0.001, 0.002), batch_size=100
    )
    result = await p.ask("test")
    assert result.startswith("[MOCK]")