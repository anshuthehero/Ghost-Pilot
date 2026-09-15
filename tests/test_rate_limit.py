"""
Tests for Rate Limiting.
"""

from server.middleware.rate_limit import RateLimiter


def test_rate_limiter_allows_under_limit():
    limiter = RateLimiter(requests_per_minute=5)
    for _ in range(5):
        assert limiter.is_rate_limited("client_1") is False


def test_rate_limiter_blocks_over_limit():
    limiter = RateLimiter(requests_per_minute=3)
    assert limiter.is_rate_limited("client_test") is False
    assert limiter.is_rate_limited("client_test") is False
    assert limiter.is_rate_limited("client_test") is False
    # 4th request within 1 minute MUST be blocked
    assert limiter.is_rate_limited("client_test") is True
