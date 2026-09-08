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

"""Persistent per-organization cache.

The cache is what makes frequent scans of a 10k member organization affordable.
Each organization gets one JSON file holding the last known members, matched
teams and repositories, each stamped with when it was read. A scan then only
re-reads what it has to:

* a cheap "meta" query gives the current member, team and repository totals for
  one rate limit point, so a changed total forces a refresh;
* anything whose stamp is older than its configured TTL is refreshed anyway,
  which covers the changes GitHub gives us no cheap signal for, such as a 2FA
  toggle or a team that gained and lost a member since the last scan;
* every scan.full_scan_every rounds the scanner ignores all of the above and
  re-reads everything, which is what reconciles deletions.

These files are JSON rather than YAML because they hold tens of thousands of
records and are rewritten on every scan, and PyYAML's serialiser is slow enough
for that to show.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import pathlib
import re
import tempfile
import time
import typing

from . import config as _config
from .ghtypes import as_dict, as_int
from .snapshot import MemberRecord, RepositoryRecord, TeamRecord

LOGGER = logging.getLogger("orgscanner.cache")

CACHE_VERSION = 2
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_organization_name(organization: str) -> str:
    """The filename stem used for an organization's cache file.

    An organization login cannot contain a path separator, but the scanner
    should not hand one to the filesystem on the strength of that alone.
    """
    return _SAFE_NAME.sub("_", organization).strip("._") or "org"

# The three kinds of data the cache tracks. Each has a matching set of
# <kind>, <kind>_total and <kind>_updated_at attributes on OrgCache.
CacheKind = typing.Literal["members", "teams", "repositories"]


class CachedTeamRecord(TeamRecord):
    """A team as cached, with the time its member list was last read."""

    refreshed_at: float


def cached_team(record: TeamRecord, refreshed_at: float) -> CachedTeamRecord:
    """Stamp a team record with the time it was read."""
    return {
        "slug": record["slug"],
        "name": record["name"],
        "id": record["id"],
        "privacy": record["privacy"],
        "member_count": record["member_count"],
        "members": record["members"],
        "refreshed_at": refreshed_at,
    }


@dataclasses.dataclass
class OrgCache:
    """Everything remembered about one organization between scans."""

    organization: str
    organization_id: int | None = None
    scan_serial: int = 0
    last_full_scan: float = 0.0
    last_scan: float = 0.0

    members: dict[str, MemberRecord] = dataclasses.field(default_factory=dict)
    members_total: int = -1
    members_updated_at: float = 0.0

    teams: dict[str, CachedTeamRecord] = dataclasses.field(default_factory=dict)
    teams_total: int = -1
    teams_updated_at: float = 0.0
    # The patterns that produced the cached team set. If an operator edits them,
    # the cached teams answer the wrong question and have to be thrown away.
    team_patterns: list[str] = dataclasses.field(default_factory=list)

    repositories: dict[str, RepositoryRecord] = dataclasses.field(default_factory=dict)
    repositories_total: int = -1
    repositories_updated_at: float = 0.0

    @property
    def is_empty(self) -> bool:
        return not (self.members or self.teams or self.repositories)

    def records(self, kind: CacheKind) -> dict[str, typing.Any]:
        """The cached records for one kind of data."""
        records: dict[str, typing.Any] = getattr(self, kind)
        return records

    def total(self, kind: CacheKind) -> int:
        """The organization total that was current when kind was last read."""
        return int(getattr(self, f"{kind}_total"))

    def age(self, kind: CacheKind) -> float:
        """Seconds since kind was last read, or inf if it never was."""
        stamp = float(getattr(self, f"{kind}_updated_at"))
        if not stamp:
            return float("inf")
        return max(0.0, time.time() - stamp)

    def is_fresh(self, kind: CacheKind, ttl: int, current_total: int | None) -> bool:
        """True if the cached kind can be reused without asking GitHub again."""
        if not self.records(kind):
            return False
        if ttl <= 0:  # A zero TTL means "never trust the cache for this"
            return False
        if self.age(kind) > ttl:
            return False
        if current_total is not None and self.total(kind) != current_total:
            return False
        return True

    def to_dict(self) -> dict[str, typing.Any]:
        data = dataclasses.asdict(self)
        data["version"] = CACHE_VERSION
        return data

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any], organization: str) -> OrgCache:
        if as_int(data.get("version"), -1) != CACHE_VERSION:
            # A format change simply invalidates the cache; the next scan is full.
            return cls(organization=organization)
        known = {field.name for field in dataclasses.fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in known}
        kwargs["organization"] = organization
        cache = cls(**kwargs)
        # A hand-edited or truncated file must not take the scanner down.
        for kind in typing.get_args(CacheKind):
            if not isinstance(getattr(cache, kind), dict):
                setattr(cache, kind, {})
                setattr(cache, f"{kind}_total", -1)
                setattr(cache, f"{kind}_updated_at", 0.0)
        if not isinstance(cache.team_patterns, list):
            cache.team_patterns = []
        return cache


class CacheStore:
    """Loads and saves OrgCache files, and does nothing when caching is off."""

    def __init__(self, config: _config.CacheConfig):
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.directory)

    def path_for(self, organization: str) -> pathlib.Path:
        directory = self.config.directory
        assert directory is not None, "Cache directory must be configured"
        return directory / f"{safe_organization_name(organization)}.cache.json"

    def load(self, organization: str) -> OrgCache:
        if not self.enabled:
            return OrgCache(organization=organization)
        path = self.path_for(organization)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return OrgCache(organization=organization)
        except (OSError, ValueError) as e:
            LOGGER.warning("Ignoring unreadable cache %s: %s", path, e)
            return OrgCache(organization=organization)
        cache = OrgCache.from_dict(as_dict(data), organization)
        LOGGER.debug(
            "Loaded cache for %s: %d members, %d teams, %d repositories",
            organization,
            len(cache.members),
            len(cache.teams),
            len(cache.repositories),
        )
        return cache

    def save(self, cache: OrgCache) -> pathlib.Path | None:
        if not self.enabled:
            return None
        path = self.path_for(cache.organization)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write and rename, so a crash mid-write cannot leave half a cache
            # behind. A corrupt file would cost us a full rescan.
            handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as f:
                    json.dump(cache.to_dict(), f)
                os.replace(tmp_name, path)
            except BaseException:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
                raise
        except OSError as e:
            LOGGER.warning("Could not write cache %s: %s", path, e)
            return None
        return path
