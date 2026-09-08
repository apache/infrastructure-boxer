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

"""The organization scanner.

One scan of one organization is:

1. a single cheap "meta" query for the organization's database ID and its
   member, team and repository totals,
2. members, teams and repositories fetched concurrently, each skipping whatever
   the cache says cannot have changed (see cache.py),
3. a snapshot written to $org-$timestamp.yaml, with old snapshots rotated out.

Every query asks for GitHub's rateLimit block, which is free and keeps the
client's idea of the remaining budget current, and every paginated sweep
carries an adaptive page size that shrinks if GitHub times out.

Teams are the expensive part of a large organization: there are thousands of
them, each with its own member list. Instead of one round trip per team,
matching teams are requested several per GraphQL document using field aliases.
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

from . import cache as _cache
from . import config as _config
from . import ghclient
from . import writer
from .ghtypes import GraphQLData, as_dict, as_int, as_list, as_optional_bool, as_optional_int, as_str, page_info
from .snapshot import Member, OrgSnapshot, Repository, ScanStats, Team

LOGGER = logging.getLogger("orgscanner.scanner")

VERSION = "1.0.0"

RATE_LIMIT_FRAGMENT = "rateLimit { limit cost remaining used resetAt }"

META_QUERY = """
query OrgMeta($org: String!) {
  organization(login: $org) {
    login
    databaseId
    membersWithRole(first: 1) { totalCount }
    teams(first: 1) { totalCount }
    repositories(first: 1) { totalCount }
  }
  %s
}
""" % RATE_LIMIT_FRAGMENT

MEMBERS_QUERY = """
query OrgMembers($org: String!, $size: Int!, $after: String) {
  organization(login: $org) {
    membersWithRole(first: $size, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      edges {
        role
        hasTwoFactorEnabled
        node { login databaseId name }
      }
    }
  }
  %s
}
""" % RATE_LIMIT_FRAGMENT

TEAMS_QUERY = """
query OrgTeams($org: String!, $size: Int!, $after: String) {
  organization(login: $org) {
    teams(first: $size, after: $after, orderBy: {field: NAME, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        slug
        name
        databaseId
        privacy
        members { totalCount }
      }
    }
  }
  %s
}
""" % RATE_LIMIT_FRAGMENT

REPOSITORIES_QUERY = """
query OrgRepositories($org: String!, $size: Int!, $after: String) {
  organization(login: $org) {
    repositories(first: $size, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        databaseId
        visibility
        url
        isArchived
        updatedAt
      }
    }
  }
  %s
}
""" % RATE_LIMIT_FRAGMENT


class OrgMeta(typing.TypedDict):
    """What the meta query tells us about an organization."""

    id: int | None
    members: int
    teams: int
    repositories: int


class TeamMeta(typing.TypedDict):
    """A team from the team listing, before its members have been read."""

    slug: str
    name: str
    id: int | None
    privacy: str
    member_count: int


@dataclasses.dataclass
class TeamScanStats:
    """How much of the team work a scan had to do."""

    refreshed: int = 0
    cached: int = 0
    all_cached: bool = False


def build_team_members_query(count: int) -> str:
    """Build a document fetching member pages for `count` teams at once.

    Slugs and cursors go in as variables ($s0, $c0 and so on) rather than being
    interpolated into the document, so a team name coming back from GitHub can
    never alter the query.
    """
    assert count > 0, "A team member batch needs at least one team"
    declarations = ["$org: String!", "$size: Int!"]
    selections = []
    for index in range(count):
        declarations.append(f"$s{index}: String!")
        declarations.append(f"$c{index}: String")
        selections.append(
            f"    t{index}: team(slug: $s{index}) {{\n"
            f"      slug\n"
            f"      members(first: $size, after: $c{index}) {{\n"
            f"        totalCount\n"
            f"        pageInfo {{ hasNextPage endCursor }}\n"
            f"        nodes {{ login }}\n"
            f"      }}\n"
            f"    }}"
        )
    return "query TeamMembers(%s) {\n  organization(login: $org) {\n%s\n  }\n  %s\n}\n" % (
        ", ".join(declarations),
        "\n".join(selections),
        RATE_LIMIT_FRAGMENT,
    )


T = typing.TypeVar("T")


def _completed(outcome: T | BaseException) -> T:
    """Re-raise a gathered failure, or hand back its result."""
    if isinstance(outcome, BaseException):
        raise outcome
    return outcome


class OrgScanner:
    """Scans GitHub organizations and writes YAML snapshots.

    Can be used one shot (await scanner.scan_all()), as a long lived task inside
    Boxer (asyncio.create_task(scanner.run_forever())), or standalone through
    python -m orgscanner. Keeping one instance around across scans keeps the
    in-memory cache and the HTTP connection pool warm.
    """

    def __init__(
        self,
        config: _config.Configuration,
        client: ghclient.QueryClient | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        self.config = config
        self.client: ghclient.QueryClient = client or ghclient.GraphQLClient(config, session=session)
        self.cache_store = _cache.CacheStore(config.cache)
        self.snapshots: dict[str, OrgSnapshot] = {}
        self.errors: dict[str, str] = {}
        self._caches: dict[str, _cache.OrgCache] = {}

    async def __aenter__(self) -> OrgScanner:
        await self.client.session()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self.client.close()

    # -- public API --------------------------------------------------------

    async def scan_all(
        self,
        organizations: typing.Sequence[str] | None = None,
        *,
        full: bool = False,
        write: bool = True,
    ) -> dict[str, OrgSnapshot]:
        """Scan every configured organization, one after the other.

        A failure on one organization is logged and recorded in self.errors, and
        the rest are still scanned. The returned mapping only holds the
        organizations that scanned successfully.
        """
        targets = list(organizations or self.config.scan.organizations)
        results: dict[str, OrgSnapshot] = {}
        self.errors = {}
        for index, org in enumerate(targets):
            if index and self.config.scan.organization_delay:
                await asyncio.sleep(self.config.scan.organization_delay)
            try:
                results[org] = await self.scan_organization(org, full=full, write=write)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # Deliberately broad: one bad org must not stop the rest
                self.errors[org] = str(e)
                LOGGER.error(
                    "Scan of organization %s failed: %s", org, e, exc_info=LOGGER.isEnabledFor(logging.DEBUG)
                )
        return results

    async def scan_organization(self, organization: str, *, full: bool = False, write: bool = True) -> OrgSnapshot:
        """Scan one organization and, by default, write its snapshot to disk."""
        started = time.time()
        cache = self._cache_for(organization)

        full_scan = bool(full or cache.is_empty or self._due_for_full_scan(cache))
        requests_before = self.client.requests
        points_before = self.client.points_spent
        retries_before = self.client.retries

        LOGGER.info(
            "Scanning organization %s (%s scan, cache serial %d)",
            organization,
            "full" if full_scan else "incremental",
            cache.scan_serial,
        )

        meta = await self._fetch_meta(organization)
        cache.organization_id = meta["id"] or cache.organization_id

        page_sizes: list[ghclient.AdaptivePageSize] = []
        # Members, teams and repositories are independent sweeps, and overlapping
        # them hides the per-request latency that dominates a large organization.
        member_outcome, team_outcome, repository_outcome = await asyncio.gather(
            self._fetch_members(organization, cache, meta["members"], full_scan, page_sizes),
            self._fetch_teams(organization, cache, meta["teams"], full_scan, page_sizes),
            self._fetch_repositories(organization, cache, meta["repositories"], full_scan, page_sizes),
            return_exceptions=True,
        )
        members, members_cached = _completed(member_outcome)
        teams, team_stats = _completed(team_outcome)
        repositories, repositories_cached = _completed(repository_outcome)

        now = time.time()
        cache.scan_serial += 1
        cache.last_scan = now
        if full_scan:
            cache.last_full_scan = now
        self.cache_store.save(cache)

        stats = ScanStats(
            full_scan=full_scan,
            started_at=started,
            finished_at=now,
            graphql_requests=self.client.requests - requests_before,
            graphql_points=self.client.points_spent - points_before,
            graphql_retries=self.client.retries - retries_before,
            rate_limit_remaining=self.client.rate_limit.remaining if self.client.rate_limit.known else None,
            rate_limit_limit=self.client.rate_limit.limit if self.client.rate_limit.known else None,
            teams_refreshed=team_stats.refreshed,
            teams_from_cache=team_stats.cached,
            repositories_from_cache=repositories_cached,
            page_size_reductions=sum(page.shrinks for page in page_sizes),
        )
        if members_cached:
            stats.reused_from_cache.append("members")
        if team_stats.all_cached:
            stats.reused_from_cache.append("teams")
        if repositories_cached and not full_scan:
            stats.reused_from_cache.append("repositories")

        snapshot = OrgSnapshot(
            organization=organization,
            organization_id=cache.organization_id,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            team_patterns=list(self.config.scan.team_patterns),
            members=members,
            teams=teams,
            repositories=repositories,
            stats=stats,
            scanner_version=VERSION,
        )
        snapshot.sort()
        self.snapshots[organization] = snapshot

        if write:
            writer.write_snapshot(self.config.output, snapshot)

        counts = snapshot.counts()
        LOGGER.info(
            "Scanned %s in %.1fs: %d members (%d without 2FA), %d matched teams, %d repositories "
            "[%d requests, %d points, %d/%d budget left]",
            organization,
            stats.duration,
            counts["members"],
            counts["members_without_2fa"],
            counts["teams"],
            counts["repositories"],
            stats.graphql_requests,
            stats.graphql_points,
            stats.rate_limit_remaining if stats.rate_limit_remaining is not None else -1,
            stats.rate_limit_limit if stats.rate_limit_limit is not None else -1,
        )
        return snapshot

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Scan every organization on a loop until stop_event is set.

        This is the entry point for the standalone daemon and for a Boxer
        background task. The wait between rounds is scan.interval measured from
        the end of the previous round, plus up to scan.jitter seconds so that
        several scanners sharing a token do not line up.
        """
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            round_started = time.time()
            try:
                await self.scan_all()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # Never let the loop die on a bad round
                LOGGER.error("Scan round failed: %s", e, exc_info=LOGGER.isEnabledFor(logging.DEBUG))
            elapsed = time.time() - round_started
            delay = max(0.0, self.config.scan.interval - elapsed)
            if self.config.scan.jitter:
                delay += random.uniform(0, self.config.scan.jitter)
            # If the hourly budget is spent, wait out the reset rather than
            # starting a round that will only park on its first query.
            budget_wait = self._budget_wait()
            if budget_wait > delay:
                LOGGER.warning(
                    "GraphQL budget nearly spent (%d left); sleeping %.0fs until it resets",
                    self.client.rate_limit.remaining,
                    budget_wait,
                )
                delay = min(budget_wait, float(self.config.performance.max_sleep))
            LOGGER.info("Scan round done in %.1fs, next round in %.0fs", elapsed, delay)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue

    # -- internals ---------------------------------------------------------

    def _cache_for(self, organization: str) -> _cache.OrgCache:
        """The cache to scan against, honouring cache.enabled."""
        previous = self._caches.get(organization)
        if not self.cache_store.enabled:
            # Caching off: carry nothing but the organization ID and the scan
            # counter across rounds, so every scan re-reads everything.
            cache = _cache.OrgCache(organization=organization)
            if previous:
                cache.organization_id = previous.organization_id
                cache.scan_serial = previous.scan_serial
        else:
            cache = previous or self.cache_store.load(organization)
        self._caches[organization] = cache
        return cache

    def _due_for_full_scan(self, cache: _cache.OrgCache) -> bool:
        every = self.config.scan.full_scan_every
        if every <= 0:
            return False
        return cache.scan_serial % every == 0

    def _budget_wait(self) -> float:
        limit = self.client.rate_limit
        if not limit.known:
            return 0.0
        if limit.remaining > self.config.performance.rate_limit_reserve:
            return 0.0
        return limit.seconds_until_reset() + 5

    def _page_size(
        self, size: int, label: str, registry: list[ghclient.AdaptivePageSize]
    ) -> ghclient.AdaptivePageSize:
        page_size = ghclient.AdaptivePageSize(size, self.config.performance.min_page_size, label)
        registry.append(page_size)
        return page_size

    async def _fetch_meta(self, organization: str) -> OrgMeta:
        """One point buys the org ID and the three totals the cache keys on."""
        data = await self.client.query(META_QUERY, {"org": organization}, label=f"meta[{organization}]")
        org = as_dict(data.get("organization"))
        if not org:
            raise ghclient.GitHubError(
                f"GitHub returned no data for organization '{organization}'. Does it exist, "
                "and does the token have access to it?"
            )
        return {
            "id": as_optional_int(org.get("databaseId")),
            "members": as_int(as_dict(org.get("membersWithRole")).get("totalCount")),
            "teams": as_int(as_dict(org.get("teams")).get("totalCount")),
            "repositories": as_int(as_dict(org.get("repositories")).get("totalCount")),
        }

    async def _fetch_members(
        self,
        organization: str,
        cache: _cache.OrgCache,
        total: int,
        full_scan: bool,
        page_sizes: list[ghclient.AdaptivePageSize],
    ) -> tuple[list[Member], bool]:
        """All organization members, with numeric ID, name and 2FA status.

        GitHub has no "changed since" filter on organization membership, so the
        cache is reused only while the member count is unchanged and the cached
        copy is younger than cache.member_ttl. That bounds how long a 2FA change
        can go unnoticed.
        """
        if not full_scan and cache.is_fresh("members", self.config.cache.member_ttl, total):
            LOGGER.info(
                "Reusing %d cached members for %s (%.0fs old, count unchanged)",
                len(cache.members),
                organization,
                cache.age("members"),
            )
            return [Member.from_dict(record) for record in cache.members.values()], True

        page_size = self._page_size(self.config.performance.member_page_size, "members", page_sizes)
        members: list[Member] = []
        cursor: str | None = None
        while True:
            data = await self.client.query(
                MEMBERS_QUERY,
                {"org": organization, "size": page_size.size, "after": cursor},
                label=f"members[{organization}]",
                page_size=page_size,
            )
            connection = _connection(data, "membersWithRole")
            for entry in as_list(connection.get("edges")):
                edge = as_dict(entry)
                node = as_dict(edge.get("node"))
                login = as_str(node.get("login"))
                if not login:  # A membership GitHub would not resolve for us
                    continue
                members.append(
                    Member(
                        login=login,
                        id=as_optional_int(node.get("databaseId")),
                        name=as_str(node.get("name")) or None,
                        two_factor_enabled=as_optional_bool(edge.get("hasTwoFactorEnabled")),
                        role=as_str(edge.get("role"), "member").lower(),
                    )
                )
            page = page_info(connection)
            if not page.more:
                break
            cursor = page.cursor

        if any(member.two_factor_enabled is None for member in members):
            LOGGER.warning(
                "GitHub did not report 2FA status for some %s members. The token needs "
                "organization owner rights (read:org) to see it.",
                organization,
            )

        cache.members = {member.login: member.to_dict() for member in members}
        cache.members_total = len(members)
        cache.members_updated_at = time.time()
        return members, False

    async def _fetch_teams(
        self,
        organization: str,
        cache: _cache.OrgCache,
        total: int,
        full_scan: bool,
        page_sizes: list[ghclient.AdaptivePageSize],
    ) -> tuple[list[Team], TeamScanStats]:
        """Teams matching the configured patterns, with their members."""
        stats = TeamScanStats()
        patterns_changed = cache.team_patterns != list(self.config.scan.team_patterns)
        if patterns_changed and cache.teams:
            LOGGER.info("Team patterns changed since the last scan of %s; re-reading teams", organization)
            cache.teams = {}
        if not full_scan and not patterns_changed and cache.is_fresh("teams", self.config.cache.team_ttl, total):
            LOGGER.info(
                "Reusing %d cached teams for %s (%.0fs old, team count unchanged)",
                len(cache.teams),
                organization,
                cache.age("teams"),
            )
            stats.cached = len(cache.teams)
            stats.all_cached = True
            return [Team.from_dict(record) for record in cache.teams.values()], stats

        matched = await self._fetch_team_list(organization, page_sizes)

        # Only re-read the member list of teams whose size changed, whose cached
        # copy has aged out, or that we have not seen before. On a settled
        # organization that is a handful of teams out of thousands.
        now = time.time()
        stale: list[TeamMeta] = []
        teams: list[Team] = []
        for meta in matched:
            cached = cache.teams.get(meta["slug"]) if not full_scan else None
            if cached and self._team_cache_usable(cached, meta, now):
                team = Team.from_dict(cached)
                team.name = meta["name"]  # Team metadata is free, take the fresh copy
                team.id = meta["id"]
                team.privacy = meta["privacy"]
                teams.append(team)
                stats.cached += 1
            else:
                stale.append(meta)

        if stale:
            refreshed = await self._fetch_team_members(organization, stale, page_sizes)
            teams.extend(refreshed)
            stats.refreshed = len(refreshed)

        cache.teams = {team.slug: _cache.cached_team(team.to_dict(), now) for team in teams}
        # The total tracked here is the organization's total team count rather
        # than the matched count: it is the change signal the meta query gives us.
        cache.teams_total = total
        cache.teams_updated_at = now
        cache.team_patterns = list(self.config.scan.team_patterns)
        return teams, stats

    def _team_cache_usable(self, cached: _cache.CachedTeamRecord, meta: TeamMeta, now: float) -> bool:
        """True if a cached team's member list can be reused as it stands."""
        ttl = self.config.cache.team_ttl
        if ttl <= 0:
            return False
        if cached.get("member_count", -1) != meta["member_count"]:
            return False
        return now - cached.get("refreshed_at", 0.0) <= ttl

    async def _fetch_team_list(
        self, organization: str, page_sizes: list[ghclient.AdaptivePageSize]
    ) -> list[TeamMeta]:
        """Every team in the organization, filtered down to the matching ones."""
        page_size = self._page_size(self.config.performance.team_page_size, "teams", page_sizes)
        matched: list[TeamMeta] = []
        seen = 0
        cursor: str | None = None
        while True:
            data = await self.client.query(
                TEAMS_QUERY,
                {"org": organization, "size": page_size.size, "after": cursor},
                label=f"teams[{organization}]",
                page_size=page_size,
            )
            connection = _connection(data, "teams")
            for entry in as_list(connection.get("nodes")):
                node = as_dict(entry)
                if not node:
                    continue
                seen += 1
                slug = as_str(node.get("slug"))
                name = as_str(node.get("name"))
                if not slug or not self.config.scan.matches_team(slug, name):
                    continue
                matched.append(
                    {
                        "slug": slug,
                        "name": name,
                        "id": as_optional_int(node.get("databaseId")),
                        "privacy": as_str(node.get("privacy")).lower(),
                        "member_count": as_int(as_dict(node.get("members")).get("totalCount")),
                    }
                )
            page = page_info(connection)
            if not page.more:
                break
            cursor = page.cursor

        LOGGER.info(
            "%s: %d of %d teams match %s", organization, len(matched), seen, self.config.scan.team_patterns
        )
        return matched

    async def _fetch_team_members(
        self,
        organization: str,
        teams: list[TeamMeta],
        page_sizes: list[ghclient.AdaptivePageSize],
    ) -> list[Team]:
        """Fetch member lists for the given teams, several teams per request."""
        page_size = self._page_size(self.config.performance.team_member_page_size, "team members", page_sizes)
        results: dict[str, Team] = {
            meta["slug"]: Team(
                slug=meta["slug"],
                name=meta["name"],
                id=meta["id"],
                privacy=meta["privacy"],
                members=[],
                member_count=meta["member_count"],
            )
            for meta in teams
        }
        # Each entry is a team still needing members, as a slug and a cursor.
        pending: list[tuple[str, str | None]] = [(meta["slug"], None) for meta in teams]
        batch_size = self.config.performance.team_batch_size

        while pending:
            batch, pending = pending[:batch_size], pending[batch_size:]
            document = build_team_members_query(len(batch))
            variables: dict[str, typing.Any] = {"org": organization, "size": page_size.size}
            for index, (slug, cursor) in enumerate(batch):
                variables[f"s{index}"] = slug
                variables[f"c{index}"] = cursor
            data = await self.client.query(
                document,
                variables,
                label=f"team-members[{organization}, {len(batch)} teams]",
                page_size=page_size,
            )
            org_data = as_dict(data.get("organization"))
            for index, (slug, _cursor) in enumerate(batch):
                node = as_dict(org_data.get(f"t{index}"))
                if not node:  # Team deleted mid-scan, or invisible to this token
                    LOGGER.warning("%s: team %s returned no data, skipping", organization, slug)
                    results.pop(slug, None)
                    continue
                connection = as_dict(node.get("members"))
                team = results[slug]
                for entry in as_list(connection.get("nodes")):
                    login = as_str(as_dict(entry).get("login"))
                    if login:
                        team.members.append(login)
                team.member_count = as_int(connection.get("totalCount"), len(team.members))
                page = page_info(connection)
                if page.more:
                    # A big team: queue its next page with the other leftovers.
                    pending.append((slug, page.cursor))

        for team in results.values():
            team.members = sorted(set(team.members))
        return list(results.values())

    async def _fetch_repositories(
        self,
        organization: str,
        cache: _cache.OrgCache,
        total: int,
        full_scan: bool,
        page_sizes: list[ghclient.AdaptivePageSize],
    ) -> tuple[list[Repository], int]:
        """All repositories, most recently updated first.

        On an incremental scan the sweep stops as soon as it reaches a repository
        GitHub last updated before our previous sweep, and the rest comes from
        the cache, since repository metadata cannot change without updatedAt
        moving. Deletions leave no trace in that ordering, so they are caught by
        the totals from the meta query (a changed count forces a full sweep) and
        by the periodic full scan.
        """
        incremental = (
            not full_scan
            and bool(cache.repositories)
            and cache.repositories_updated_at > 0
            and cache.repositories_total == total
            and self.config.cache.repository_ttl > 0
            and cache.age("repositories") <= self.config.cache.repository_ttl
        )
        cutoff = 0.0
        if incremental:
            cutoff = cache.repositories_updated_at - self.config.cache.incremental_overlap

        page_size = self._page_size(self.config.performance.repository_page_size, "repositories", page_sizes)
        repositories: dict[str, Repository] = {}
        cursor: str | None = None
        stopped_early = False
        while not stopped_early:
            data = await self.client.query(
                REPOSITORIES_QUERY,
                {"org": organization, "size": page_size.size, "after": cursor},
                label=f"repositories[{organization}]",
                page_size=page_size,
            )
            connection = _connection(data, "repositories")
            for entry in as_list(connection.get("nodes")):
                node = as_dict(entry)
                name = as_str(node.get("name"))
                if not name:
                    continue
                updated_at = as_str(node.get("updatedAt"))
                if incremental and updated_at and ghclient.parse_timestamp(updated_at) < cutoff:
                    stopped_early = True
                    break
                repositories[name] = Repository(
                    name=name,
                    id=as_optional_int(node.get("databaseId")),
                    visibility=as_str(node.get("visibility"), "public").lower(),
                    url=as_str(node.get("url"), f"https://github.com/{organization}/{name}"),
                    archived=bool(node.get("isArchived")),
                    updated_at=updated_at or None,
                )
            if stopped_early:
                break
            page = page_info(connection)
            if not page.more:
                break
            cursor = page.cursor

        reused = 0
        if incremental:
            for name, record in cache.repositories.items():
                if name not in repositories:
                    repositories[name] = Repository.from_dict(record)
                    reused += 1
            LOGGER.info(
                "%s: refreshed %d repositories, reused %d unchanged from cache",
                organization,
                len(repositories) - reused,
                reused,
            )

        cache.repositories = {name: repo.to_dict() for name, repo in repositories.items()}
        cache.repositories_total = total
        cache.repositories_updated_at = time.time()
        if len(repositories) != total:
            # Either the organization changed under us mid-scan, or an
            # incremental sweep has drifted. Either way, scan it all next time.
            LOGGER.warning(
                "%s: found %d repositories but GitHub reports %d; forcing a full sweep next round",
                organization,
                len(repositories),
                total,
            )
            cache.repositories_total = -1
        return list(repositories.values()), reused


def _connection(data: GraphQLData, name: str) -> GraphQLData:
    """Pull one connection out of an organization query response."""
    return as_dict(as_dict(data.get("organization")).get(name))


async def scan_once(
    config: _config.Configuration | str,
    organizations: typing.Sequence[str] | None = None,
    *,
    full: bool = False,
    write: bool = True,
) -> dict[str, OrgSnapshot]:
    """Run a single scan of every configured organization.

    config may be a Configuration or the path to a YAML config file. This is the
    simplest way for Boxer to call the scanner from one of its own background
    tasks:

        snapshots = await orgscanner.scan_once("orgscanner.yaml")
    """
    configuration = config if isinstance(config, _config.Configuration) else _config.load_config(config)
    async with OrgScanner(configuration) as scanner:
        return await scanner.scan_all(organizations, full=full, write=write)


async def run_forever(
    config: _config.Configuration | str,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run the scan loop until stop_event is set."""
    configuration = config if isinstance(config, _config.Configuration) else _config.load_config(config)
    async with OrgScanner(configuration) as scanner:
        await scanner.run_forever(stop_event)
