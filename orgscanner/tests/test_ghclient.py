"""Tests for the GraphQL client's rate limiting, retries and error handling"""
from __future__ import annotations

import asyncio
import datetime
import time
import typing

import pytest

from orgscanner import config as _config
from orgscanner import ghclient
from orgscanner.ghtypes import GraphQLData


def make_client(**performance: typing.Any) -> ghclient.GraphQLClient:
    settings: dict[str, typing.Any] = {
        "github": {"token": "x" * 40},
        "scan": {"organizations": ["apache"]},
        "performance": {"max_retries": 3, "retry_backoff": 1.0, **performance},
    }
    return ghclient.GraphQLClient(_config.Configuration.from_dict(settings))


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Retries and rate limit parking must not stall the test suite for real"""
    slept: list[float] = []

    async def fake_sleep(seconds: float, *args: typing.Any, **kwargs: typing.Any) -> None:
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return slept


# -- adaptive page sizing ---------------------------------------------------


def test_page_size_halves_on_timeout_and_stops_at_the_floor() -> None:
    page = ghclient.AdaptivePageSize(100, minimum=10, label="members")
    assert page.shrink() == 50
    assert page.shrink() == 25
    assert page.shrink() == 12
    assert page.shrink() == 10
    assert page.shrink() == 10  # Floor
    assert page.shrinks == 4  # The no-op shrink is not counted


def test_page_size_grows_back_after_a_clean_run() -> None:
    page = ghclient.AdaptivePageSize(100, minimum=5, label="repositories")
    page.shrink()
    for _ in range(5):
        page.success()
    assert page.size > 50
    for _ in range(50):
        page.success()
    assert page.size == 100  # Never above the configured size


def test_page_size_floor_is_clamped_to_the_starting_size() -> None:
    page = ghclient.AdaptivePageSize(4, minimum=10, label="tiny")
    assert page.minimum == 4
    assert page.shrink() == 4


# -- rate limit accounting --------------------------------------------------


def test_the_rate_limit_block_is_recorded_from_every_response() -> None:
    client = make_client()
    client._note_rate_limit(
        {"rateLimit": {"limit": 5000, "cost": 7, "remaining": 4321, "used": 679, "resetAt": "2026-09-08T13:00:00Z"}}
    )
    assert client.rate_limit.remaining == 4321
    assert client.rate_limit.limit == 5000
    assert client.points_spent == 7
    assert client.rate_limit.known


def test_a_response_without_a_rate_limit_block_is_harmless() -> None:
    client = make_client()
    client._note_rate_limit({"organization": {}})
    assert not client.rate_limit.known


def test_the_client_parks_when_the_budget_hits_the_reserve(no_real_sleeping: list[float]) -> None:
    client = make_client(rate_limit_reserve=100)
    client.rate_limit = ghclient.RateLimit(
        limit=5000, remaining=50, used=4950, reset_at=time.time() + 600, updated_at=time.time()
    )
    asyncio.run(client._await_budget())
    assert no_real_sleeping, "expected the client to wait for the budget to reset"
    assert no_real_sleeping[0] > 500
    # Having waited, it assumes the budget is back rather than parking forever
    assert client.rate_limit.remaining == 5000


def test_concurrent_callers_wait_out_one_reset_window_between_them(no_real_sleeping: list[float]) -> None:
    """One window between them, rather than one each, which would park for hours"""
    client = make_client(rate_limit_reserve=100, concurrency=8)
    client.rate_limit = ghclient.RateLimit(
        limit=5000, remaining=10, used=4990, reset_at=time.time() + 300, updated_at=time.time()
    )

    async def run() -> None:
        await asyncio.gather(*[client._await_budget() for _ in range(8)])

    asyncio.run(run())
    assert len(no_real_sleeping) == 1


def test_no_parking_while_there_is_budget_left(no_real_sleeping: list[float]) -> None:
    client = make_client(rate_limit_reserve=100)
    client.rate_limit = ghclient.RateLimit(
        limit=5000, remaining=4000, used=1000, reset_at=time.time() + 600, updated_at=time.time()
    )
    asyncio.run(client._await_budget())
    assert no_real_sleeping == []


def test_sleeps_are_capped_by_max_sleep(no_real_sleeping: list[float]) -> None:
    client = make_client(max_sleep=60)
    asyncio.run(client._sleep(9999, "test"))
    assert no_real_sleeping == [60]


# -- error classification ---------------------------------------------------


def test_a_rate_limited_error_is_retried_after_the_reset() -> None:
    client = make_client()
    client.rate_limit = ghclient.RateLimit(reset_at=time.time() + 120, updated_at=time.time())
    with pytest.raises(ghclient._Transient) as exc:
        client._raise_for_errors([{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}], {}, "q")
    retry_after = exc.value.retry_after
    assert retry_after is not None and retry_after > 100


def test_a_github_execution_timeout_is_flagged_as_a_timeout() -> None:
    client = make_client()
    with pytest.raises(ghclient._Transient) as exc:
        client._raise_for_errors(
            [{"message": "Something went wrong while executing your query. Please try again"}], {}, "q"
        )
    assert exc.value.timeout is True


def test_a_missing_organization_is_not_retried() -> None:
    client = make_client()
    with pytest.raises(ghclient.GitHubQueryError):
        client._raise_for_errors([{"type": "NOT_FOUND", "message": "Could not resolve to an Organization"}], {}, "q")


def test_a_soft_error_alongside_data_is_logged_and_survived() -> None:
    """GitHub often reports a suspended user in an otherwise fine response"""
    client = make_client()
    client._raise_for_errors([{"message": "user is suspended"}], {"organization": {"login": "apache"}}, "q")


def test_an_error_with_no_data_is_retried() -> None:
    client = make_client()
    with pytest.raises(ghclient._Transient):
        client._raise_for_errors([{"message": "unexplained failure"}], {}, "q")


# -- retry loop -------------------------------------------------------------


def test_a_transient_failure_is_retried_and_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    attempts: list[str] = []

    async def flaky(document: str, variables: dict[str, typing.Any], label: str) -> GraphQLData:
        attempts.append(label)
        if len(attempts) < 3:
            raise ghclient._Transient("connection error")
        return {"ok": True}

    monkeypatch.setattr(client, "_post", flaky)
    assert asyncio.run(client.query("query Q {}", {}, label="q")) == {"ok": True}
    assert len(attempts) == 3
    assert client.retries == 2


def test_a_timeout_shrinks_the_page_size_before_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client()
    page = ghclient.AdaptivePageSize(100, minimum=5, label="members")
    sizes: list[int] = []

    async def timing_out(document: str, variables: dict[str, typing.Any], label: str) -> GraphQLData:
        sizes.append(int(variables["size"]))
        if len(sizes) < 3:
            raise ghclient._Transient("query timed out", timeout=True)
        return {"ok": True}

    monkeypatch.setattr(client, "_post", timing_out)
    asyncio.run(client.query("query Q {}", {"size": page.size}, page_size=page))
    assert sizes == [100, 50, 25]


def test_retries_are_not_infinite(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(max_retries=2)

    async def always_failing(document: str, variables: dict[str, typing.Any], label: str) -> GraphQLData:
        raise ghclient._Transient("nope")

    monkeypatch.setattr(client, "_post", always_failing)
    with pytest.raises(ghclient.GitHubError) as exc:
        asyncio.run(client.query("query Q {}", {}, label="doomed"))
    assert "giving up after 3 attempts" in str(exc.value)


def test_secondary_rate_limit_headers_are_honoured() -> None:
    assert ghclient._retry_after({"Retry-After": "42"}) == 42.0
    reset = ghclient._retry_after({"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(time.time()) + 30)})
    assert reset is not None and 25 < reset < 45
    assert ghclient._retry_after({}) == 60.0  # GitHub's documented fallback


def test_timestamps_parse_and_degrade_gracefully() -> None:
    expected = datetime.datetime(2026, 9, 8, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
    assert ghclient.parse_timestamp("2026-09-08T12:00:00Z") == pytest.approx(expected, abs=1)
    # An unparseable stamp must not become "now", or a caller would stop waiting
    assert ghclient.parse_timestamp("nonsense") > time.time() + 3000


def test_the_auth_header_uses_a_bearer_token() -> None:
    client = make_client()
    assert client.headers["Authorization"] == "bearer " + "x" * 40
    assert client.headers["User-Agent"] == "ASF-Boxer-OrgScanner"
