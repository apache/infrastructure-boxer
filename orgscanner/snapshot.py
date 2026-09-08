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

"""Data model for one organization scan.

The TypedDicts here are also the on-disk YAML schema. OrgSnapshot.to_dict() is
what gets written to $org-$timestamp.yaml and from_dict() reads one back, so
Boxer, an operator or a test can all round-trip a snapshot.

Values read back from YAML are coerced rather than trusted: a snapshot may have
been written by an older version of the scanner, or edited by hand.
"""
from __future__ import annotations

import dataclasses
import datetime
import typing

from .ghtypes import as_bool, as_dict, as_int, as_list, as_optional_bool, as_optional_int, as_optional_str, as_str


class MemberRecord(typing.TypedDict):
    """One member as stored in a snapshot."""

    login: str
    id: int | None
    name: str | None
    two_factor_enabled: bool | None
    role: str


class TeamRecord(typing.TypedDict):
    """One team as stored in a snapshot."""

    slug: str
    name: str
    id: int | None
    privacy: str
    member_count: int
    members: list[str]


class RepositoryRecord(typing.TypedDict):
    """One repository as stored in a snapshot."""

    name: str
    id: int | None
    visibility: str
    private: bool
    url: str
    archived: bool
    updated_at: str | None


class ScanRecord(typing.TypedDict):
    """The scan: block of a snapshot."""

    full_scan: bool
    started_at: str | None
    finished_at: str | None
    duration: float
    graphql_requests: int
    graphql_points: int
    graphql_retries: int
    rate_limit_remaining: int | None
    rate_limit_limit: int | None
    reused_from_cache: list[str]
    teams_refreshed: int
    teams_from_cache: int
    repositories_from_cache: int
    page_size_reductions: int


class CountsRecord(typing.TypedDict):
    """The counts: block of a snapshot."""

    members: int
    members_without_2fa: int
    members_unknown_2fa: int
    teams: int
    team_members: int
    repositories: int
    repositories_public: int
    repositories_private: int


class SnapshotRecord(typing.TypedDict):
    """A whole snapshot file."""

    organization: str
    organization_id: int | None
    timestamp: str
    scanner_version: str
    team_patterns: list[str]
    scan: ScanRecord
    counts: CountsRecord
    members: list[MemberRecord]
    teams: list[TeamRecord]
    repositories: list[RepositoryRecord]


@dataclasses.dataclass
class Member:
    """An organization member and their 2FA status.

    two_factor_enabled is None when GitHub would not tell us, which happens
    when the token does not belong to an organization owner.
    """

    login: str
    id: int | None = None
    name: str | None = None
    two_factor_enabled: bool | None = None
    role: str = "member"

    def to_dict(self) -> MemberRecord:
        return {
            "login": self.login,
            "id": self.id,
            "name": self.name,
            "two_factor_enabled": self.two_factor_enabled,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any]) -> Member:
        return cls(
            login=as_str(data.get("login")),
            id=as_optional_int(data.get("id")),
            name=as_optional_str(data.get("name")),
            two_factor_enabled=as_optional_bool(data.get("two_factor_enabled")),
            role=as_str(data.get("role"), "member"),
        )


@dataclasses.dataclass
class Team:
    """A team matching one of the configured patterns, and its members."""

    slug: str
    name: str = ""
    id: int | None = None
    privacy: str = ""
    members: list[str] = dataclasses.field(default_factory=list)
    member_count: int = 0

    def to_dict(self) -> TeamRecord:
        return {
            "slug": self.slug,
            "name": self.name,
            "id": self.id,
            "privacy": self.privacy,
            "member_count": self.member_count,
            "members": sorted(self.members),
        }

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any]) -> Team:
        members = [as_str(login) for login in as_list(data.get("members")) if as_str(login)]
        return cls(
            slug=as_str(data.get("slug")),
            name=as_str(data.get("name")),
            id=as_optional_int(data.get("id")),
            privacy=as_str(data.get("privacy")),
            members=members,
            member_count=as_int(data.get("member_count"), len(members)),
        )


@dataclasses.dataclass
class Repository:
    """A repository in the organization.

    visibility is GitHub's own enum, lowercased: public, private or internal.
    """

    name: str
    id: int | None = None
    visibility: str = "public"
    url: str = ""
    archived: bool = False
    updated_at: str | None = None

    @property
    def private(self) -> bool:
        return self.visibility != "public"

    def to_dict(self) -> RepositoryRecord:
        return {
            "name": self.name,
            "id": self.id,
            "visibility": self.visibility,
            "private": self.private,
            "url": self.url,
            "archived": self.archived,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any]) -> Repository:
        visibility = as_str(data.get("visibility")).lower()
        if not visibility:  # Tolerate a snapshot that only carries `private`
            visibility = "private" if as_bool(data.get("private")) else "public"
        return cls(
            name=as_str(data.get("name")),
            id=as_optional_int(data.get("id")),
            visibility=visibility,
            url=as_str(data.get("url")),
            archived=as_bool(data.get("archived")),
            updated_at=as_optional_str(data.get("updated_at")),
        )


@dataclasses.dataclass
class ScanStats:
    """How the scan itself went. These are the numbers to tune a schedule by."""

    full_scan: bool = False
    started_at: float = 0.0
    finished_at: float = 0.0
    graphql_requests: int = 0
    graphql_points: int = 0
    graphql_retries: int = 0
    rate_limit_remaining: int | None = None
    rate_limit_limit: int | None = None
    reused_from_cache: list[str] = dataclasses.field(default_factory=list)
    teams_refreshed: int = 0
    teams_from_cache: int = 0
    repositories_from_cache: int = 0
    page_size_reductions: int = 0

    @property
    def duration(self) -> float:
        if not (self.started_at and self.finished_at):
            return 0.0
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> ScanRecord:
        return {
            "full_scan": self.full_scan,
            "started_at": _isoformat(self.started_at),
            "finished_at": _isoformat(self.finished_at),
            "duration": round(self.duration, 2),
            "graphql_requests": self.graphql_requests,
            "graphql_points": self.graphql_points,
            "graphql_retries": self.graphql_retries,
            "rate_limit_remaining": self.rate_limit_remaining,
            "rate_limit_limit": self.rate_limit_limit,
            "reused_from_cache": sorted(self.reused_from_cache),
            "teams_refreshed": self.teams_refreshed,
            "teams_from_cache": self.teams_from_cache,
            "repositories_from_cache": self.repositories_from_cache,
            "page_size_reductions": self.page_size_reductions,
        }


@dataclasses.dataclass
class OrgSnapshot:
    """The result of scanning one organization."""

    organization: str
    organization_id: int | None = None
    timestamp: datetime.datetime | None = None
    team_patterns: list[str] = dataclasses.field(default_factory=list)
    members: list[Member] = dataclasses.field(default_factory=list)
    teams: list[Team] = dataclasses.field(default_factory=list)
    repositories: list[Repository] = dataclasses.field(default_factory=list)
    stats: ScanStats = dataclasses.field(default_factory=ScanStats)
    scanner_version: str = ""

    def sort(self) -> None:
        """Sort every collection, so consecutive snapshots diff cleanly."""
        self.members.sort(key=lambda m: m.login.lower())
        self.teams.sort(key=lambda t: t.slug.lower())
        self.repositories.sort(key=lambda r: r.name.lower())

    @property
    def members_by_login(self) -> dict[str, Member]:
        return {member.login: member for member in self.members}

    @property
    def teams_by_slug(self) -> dict[str, Team]:
        return {team.slug: team for team in self.teams}

    def counts(self) -> CountsRecord:
        return {
            "members": len(self.members),
            "members_without_2fa": len([m for m in self.members if m.two_factor_enabled is False]),
            "members_unknown_2fa": len([m for m in self.members if m.two_factor_enabled is None]),
            "teams": len(self.teams),
            "team_members": sum(len(t.members) for t in self.teams),
            "repositories": len(self.repositories),
            "repositories_public": len([r for r in self.repositories if not r.private]),
            "repositories_private": len([r for r in self.repositories if r.private]),
        }

    def to_dict(self) -> SnapshotRecord:
        self.sort()
        timestamp = self.timestamp or datetime.datetime.now(datetime.timezone.utc)
        return {
            "organization": self.organization,
            "organization_id": self.organization_id,
            "timestamp": timestamp.isoformat(),
            "scanner_version": self.scanner_version,
            "team_patterns": list(self.team_patterns),
            "scan": self.stats.to_dict(),
            "counts": self.counts(),
            "members": [m.to_dict() for m in self.members],
            "teams": [t.to_dict() for t in self.teams],
            "repositories": [r.to_dict() for r in self.repositories],
        }

    @classmethod
    def from_dict(cls, data: typing.Mapping[str, typing.Any]) -> OrgSnapshot:
        return cls(
            organization=as_str(data.get("organization")),
            organization_id=as_optional_int(data.get("organization_id")),
            timestamp=_parse_isoformat(data.get("timestamp")),
            team_patterns=[as_str(p) for p in as_list(data.get("team_patterns")) if as_str(p)],
            members=[Member.from_dict(as_dict(m)) for m in as_list(data.get("members"))],
            teams=[Team.from_dict(as_dict(t)) for t in as_list(data.get("teams"))],
            repositories=[Repository.from_dict(as_dict(r)) for r in as_list(data.get("repositories"))],
            scanner_version=as_str(data.get("scanner_version")),
        )


def _isoformat(stamp: float) -> str | None:
    if not stamp:
        return None
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).isoformat()


def _parse_isoformat(value: object) -> datetime.datetime | None:
    text = as_optional_str(value)
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
