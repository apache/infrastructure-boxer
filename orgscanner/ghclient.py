#!/usr/bin/env python3
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""A rate limit aware GitHub GraphQL client.

Everything the scanner knows about GitHub's failure modes lives here:

* the hourly GraphQL point budget, read from the rateLimit block that every
  scanner query asks for (asking is free),
* primary rate limiting, where the client parks until the budget resets,
* secondary rate limiting, where it honours Retry-After and x-ratelimit-reset,
* GitHub timing out on large pages. That arrives either as a 502 or as a 200
  carrying "Something went wrong while executing your query", and the answer is
  to shrink the page size rather than send the same doomed query again.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import random
import time
import typing

import aiohttp

from . import config as _config
from .ghtypes import GraphQLData, as_dict, as_list, as_str

LOGGER = logging.getLogger("orgscanner.github")

# GitHub's wording when a query exceeds its internal execution deadline.
TIMEOUT_MARKERS = (
    "something went wrong while executing your query",
    "timeout",
    "timed out",
)


class GitHubError(Exception):
    """A GraphQL query failed in a way that is not worth retrying."""


class GitHubQueryError(GitHubError):
    """GitHub returned an errors block we cannot recover from."""

    def __init__(self, message: str, errors: list[typing.Any] | None = None):
        super().__init__(message)
        self.errors: list[typing.Any] = errors or []


class _Transient(Exception):
    """Internal: a failure that is worth another attempt."""

    def __init__(self, reason: str, retry_after: float | None = None, timeout: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after
        self.timeout = timeout


@dataclasses.dataclass
class RateLimit:
    """The last known state of the hourly GraphQL point budget."""

    limit: int = 5000
    remaining: int = 5000
    used: int = 0
    cost: int = 0
    reset_at: float = 0.0
    updated_at: float = 0.0

    @property
    def known(self) -> bool:
        return self.updated_at > 0

    def seconds_until_reset(self) -> float:
        return max(0.0, self.reset_at - time.time())


class AdaptivePageSize:
    """A page size that shrinks when GitHub times out and creeps back up.

    GitHub's GraphQL endpoint gets flaky on large pages for big organizations;
    Boxer's own team loader had to be pinned at 20 results for that reason.
    Rather than pinning everything low forever, each paginated sweep gets one of
    these. It starts at the configured size, halves on a timeout, and grows back
    after a run of clean responses.
    """

    def __init__(self, size: int, minimum: int = 5, label: str = "page"):
        self.initial = max(1, int(size))
        self.minimum = max(1, min(int(minimum), self.initial))
        self.size = self.initial
        self.label = label
        self.shrinks = 0
        self._clean_runs = 0

    def shrink(self) -> int:
        previous = self.size
        self.size = max(self.minimum, self.size // 2)
        self._clean_runs = 0
        if self.size != previous:
            self.shrinks += 1
            LOGGER.warning("GitHub timed out on %s; reducing page size %d -> %d", self.label, previous, self.size)
        return self.size

    def success(self) -> None:
        if self.size >= self.initial:
            return
        self._clean_runs += 1
        if self._clean_runs >= 5:
            previous = self.size
            self.size = min(self.initial, max(self.size + 1, int(self.size * 1.5)))
            self._clean_runs = 0
            LOGGER.info("Growing %s page size %d -> %d after a clean run", self.label, previous, self.size)


@typing.runtime_checkable
class QueryClient(typing.Protocol):
    """What the scanner needs from a GraphQL client.

    GraphQLClient below is the implementation; the scanner takes the protocol so
    tests can hand it a fake endpoint and still be type checked.
    """

    requests: int
    points_spent: int
    retries: int
    rate_limit: RateLimit

    async def query(
        self,
        document: str,
        variables: typing.Mapping[str, typing.Any] | None = None,
        *,
        label: str = ...,
        page_size: AdaptivePageSize | None = ...,
        page_size_variable: str = ...,
    ) -> GraphQLData: ...

    async def session(self) -> object: ...

    async def close(self) -> None: ...


class GraphQLClient:
    """Async GraphQL client with retries, pacing and rate limit parking."""

    def __init__(self, config: _config.Configuration, session: aiohttp.ClientSession | None = None):
        self.config = config
        self.rate_limit = RateLimit()
        self.requests = 0
        self.points_spent = 0
        self.retries = 0
        self._session = session
        self._owns_session = session is None
        self._semaphore = asyncio.Semaphore(config.performance.concurrency)
        # Serialises the "everyone hold off" decision, so concurrent queries
        # wait out one reset window between them.
        self._gate = asyncio.Lock()
        self._pace_lock = asyncio.Lock()
        self._last_request = 0.0

    # -- session plumbing ---------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": "bearer %s" % self.config.github.token,
            "User-Agent": self.config.github.user_agent,
            "Accept": "application/json",
        }

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=None, sock_connect=30, sock_read=self.config.performance.request_timeout
            )
            self._session = aiohttp.ClientSession(headers=self.headers, timeout=timeout)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> GraphQLClient:
        await self.session()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.close()

    # -- pacing and rate limiting ------------------------------------------

    async def _sleep(self, seconds: float, reason: str) -> None:
        seconds = min(max(seconds, 0.0), float(self.config.performance.max_sleep))
        if seconds <= 0:
            return
        LOGGER.warning("Pausing GitHub queries for %.0f seconds: %s", seconds, reason)
        await asyncio.sleep(seconds)

    async def _await_budget(self) -> None:
        """Park if the hourly point budget is down to the configured reserve.

        The wait happens while holding the gate, and the state is checked again
        after acquiring it, so a hundred queries hitting the reserve at once
        wait out one reset window between them instead of one each.
        """
        reserve = self.config.performance.rate_limit_reserve
        if not self.rate_limit.known or reserve <= 0:
            return
        if self.rate_limit.remaining > reserve:
            return
        async with self._gate:
            if self.rate_limit.remaining > reserve:  # Someone else already waited
                return
            wait = self.rate_limit.seconds_until_reset() + 5
            if wait > 0:
                await self._sleep(
                    wait,
                    "GraphQL budget down to %d/%d points (reserve %d)"
                    % (self.rate_limit.remaining, self.rate_limit.limit, reserve),
                )
            # Assume the budget came back; the next response will correct us.
            self.rate_limit.remaining = self.rate_limit.limit
            self.rate_limit.reset_at = time.time() + 3600

    async def _pace(self) -> None:
        interval = self.config.performance.min_request_interval
        if interval <= 0:
            return
        async with self._pace_lock:
            delta = time.time() - self._last_request
            if delta < interval:
                await asyncio.sleep(interval - delta)
            self._last_request = time.time()

    def _note_rate_limit(self, data: GraphQLData) -> None:
        block = as_dict(data.get("rateLimit"))
        if not block:
            return
        cost = _as_number(block.get("cost"), 0)
        self.points_spent += cost
        self.rate_limit.cost = cost
        self.rate_limit.limit = _as_number(block.get("limit"), self.rate_limit.limit)
        self.rate_limit.remaining = _as_number(block.get("remaining"), self.rate_limit.remaining)
        self.rate_limit.used = _as_number(block.get("used"), self.rate_limit.used)
        reset_at = as_str(block.get("resetAt"))
        if reset_at:
            self.rate_limit.reset_at = parse_timestamp(reset_at)
        self.rate_limit.updated_at = time.time()

    # -- querying ----------------------------------------------------------

    async def query(
        self,
        document: str,
        variables: typing.Mapping[str, typing.Any] | None = None,
        *,
        label: str = "query",
        page_size: AdaptivePageSize | None = None,
        page_size_variable: str = "size",
    ) -> GraphQLData:
        """Run a GraphQL document, retrying transient failures.

        If page_size is given, a GitHub timeout shrinks it and the retry goes
        out with the smaller page, instead of repeating the query that just blew
        GitHub's execution deadline.
        """
        query_variables: dict[str, typing.Any] = dict(variables or {})
        attempt = 0
        while True:
            await self._await_budget()
            await self._pace()
            try:
                async with self._semaphore:
                    data = await self._post(document, query_variables, label)
            except _Transient as transient:
                attempt += 1
                self.retries += 1
                if transient.timeout and page_size is not None:
                    query_variables[page_size_variable] = page_size.shrink()
                if attempt > self.config.performance.max_retries:
                    raise GitHubError(
                        f"{label}: giving up after {attempt} attempts, last error: {transient.reason}"
                    ) from transient
                delay = transient.retry_after
                if delay is None:
                    backoff = self.config.performance.retry_backoff**attempt
                    delay = min(backoff, 60.0) + random.uniform(0, 1)
                LOGGER.warning(
                    "%s: %s (attempt %d/%d), retrying in %.1fs",
                    label,
                    transient.reason,
                    attempt,
                    self.config.performance.max_retries,
                    delay,
                )
                await asyncio.sleep(min(delay, float(self.config.performance.max_sleep)))
                continue
            if page_size is not None:
                page_size.success()
            return data

    async def _post(self, document: str, variables: dict[str, typing.Any], label: str) -> GraphQLData:
        session = await self.session()
        payload = {"query": document, "variables": variables}
        try:
            async with session.post(self.config.github.graphql_url, json=payload) as response:
                self.requests += 1
                if response.status in (500, 502, 503, 504):
                    body = (await response.text())[:200]
                    raise _Transient(f"HTTP {response.status} from GitHub: {body}", timeout=True)
                if response.status in (403, 429):
                    raise _Transient(
                        "HTTP %d (rate limited or abuse detection)" % response.status,
                        retry_after=_retry_after(response.headers),
                    )
                if response.status == 401:
                    raise GitHubError("GitHub rejected the token (HTTP 401), check github.token")
                if response.status != 200:
                    body = (await response.text())[:200]
                    raise GitHubError(f"Unexpected HTTP {response.status} from GitHub: {body}")
                try:
                    js = as_dict(await response.json())
                except (aiohttp.ContentTypeError, ValueError) as e:
                    raise _Transient(f"Could not decode GitHub response as JSON: {e}") from e
        except asyncio.TimeoutError as e:
            raise _Transient("request timed out", timeout=True) from e
        except aiohttp.ClientError as e:
            raise _Transient(f"connection error: {e}") from e

        data = as_dict(js.get("data"))
        self._note_rate_limit(data)
        errors = as_list(js.get("errors"))
        if errors:
            self._raise_for_errors(errors, data, label)
        if not data:
            raise _Transient("GitHub returned an empty data block")
        return data

    def _raise_for_errors(self, errors: list[typing.Any], data: GraphQLData, label: str) -> None:
        """Sort a GraphQL errors block into retry, give up, or carry on."""
        messages = [as_str(as_dict(error).get("message"), str(error)) for error in errors]
        joined = "; ".join(messages)
        lowered = joined.lower()
        types = {as_str(as_dict(error).get("type")) for error in errors}

        if "RATE_LIMITED" in types or "api rate limit exceeded" in lowered:
            wait = self.rate_limit.seconds_until_reset() + 5 if self.rate_limit.known else 300
            raise _Transient(f"rate limited: {joined}", retry_after=wait)
        if any(marker in lowered for marker in TIMEOUT_MARKERS):
            raise _Transient(f"GitHub query timed out: {joined}", timeout=True)
        if "NOT_FOUND" in types:
            raise GitHubQueryError(f"{label}: {joined}", errors)
        if data:
            # Partial data with a soft error, such as a suspended account inside
            # a connection, is common and survivable. Log it and keep the data.
            LOGGER.warning("%s: GitHub reported errors but returned data: %s", label, joined)
            return
        raise _Transient(f"GitHub error: {joined}")


def _as_number(value: object, default: int) -> int:
    """Read an integer out of a rateLimit block."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return int(value)


def _retry_after(headers: typing.Mapping[str, str]) -> float | None:
    """Work out how long GitHub wants us to wait, from its documented headers."""
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    if headers.get("x-ratelimit-remaining") == "0":
        reset = headers.get("x-ratelimit-reset")
        if reset:
            try:
                return max(0.0, float(reset) - time.time()) + 5
            except ValueError:
                pass
    return 60.0  # GitHub's guidance for a secondary limit with no hint attached


def parse_timestamp(value: str) -> float:
    """Parse an ISO-8601 timestamp. GitHub always sends UTC stamps ending in Z.

    An unparseable stamp becomes an hour from now rather than the current time,
    so a caller waiting for a rate limit reset does not stop waiting early.
    """
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return time.time() + 3600
