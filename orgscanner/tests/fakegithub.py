"""A fake GitHub GraphQL endpoint, good enough to drive a whole scan.

It answers the five documents the scanner sends (org meta, members, teams, team
members, repositories) out of plain Python lists, honouring first/after
pagination and the alias batching the team loader relies on. It also counts
requests, so tests can check that the cache really did save work.

FakeGitHub is typed against ghclient.QueryClient, which is what OrgScanner
takes, so the fake and the real client are checked against the same interface.
"""
from __future__ import annotations

import time
import typing

from orgscanner import ghclient
from orgscanner.ghtypes import GraphQLData


class FakeMember(typing.TypedDict, total=False):
    """One member of the fake organization."""

    login: str
    id: int
    name: str
    two_factor: bool
    role: str


class FakeTeam(typing.TypedDict, total=False):
    """One team of the fake organization."""

    slug: str
    name: str
    id: int
    privacy: str
    members: list[str]


class FakeRepository(typing.TypedDict, total=False):
    """One repository of the fake organization."""

    name: str
    id: int
    visibility: str
    url: str
    archived: bool
    updated_at: str


class FakeGitHub:
    """Stand-in for orgscanner.ghclient.GraphQLClient."""

    def __init__(
        self,
        members: list[FakeMember] | None = None,
        teams: list[FakeTeam] | None = None,
        repositories: list[FakeRepository] | None = None,
        org_id: int = 47359,
    ):
        self.members: list[FakeMember] = members or []
        self.teams: list[FakeTeam] = teams or []
        self.repositories: list[FakeRepository] = repositories or []
        self.org_id = org_id
        self.requests = 0
        self.points_spent = 0
        self.retries = 0
        self.rate_limit = ghclient.RateLimit(
            limit=5000, remaining=4990, used=10, reset_at=time.time() + 3600, updated_at=time.time()
        )
        self.labels: list[str] = []
        self.closed = False

    # -- the plumbing the scanner expects ----------------------------------

    async def session(self) -> object:
        return None

    async def close(self) -> None:
        self.closed = True

    def request_count(self, kind: str) -> int:
        """How many requests carried a label starting with kind."""
        return len([label for label in self.labels if label.startswith(kind)])

    # -- the endpoint -------------------------------------------------------

    async def query(
        self,
        document: str,
        variables: typing.Mapping[str, typing.Any] | None = None,
        *,
        label: str = "query",
        page_size: ghclient.AdaptivePageSize | None = None,
        page_size_variable: str = "size",
    ) -> GraphQLData:
        query_variables: dict[str, typing.Any] = dict(variables or {})
        self.requests += 1
        self.points_spent += 1
        self.labels.append(label)
        if page_size is not None:
            page_size.success()
        if "OrgMeta" in document:
            return self._meta()
        if "OrgMembers" in document:
            return self._members(query_variables)
        if "OrgTeams" in document:
            return self._team_list(query_variables)
        if "TeamMembers" in document:
            return self._team_members(query_variables)
        if "OrgRepositories" in document:
            return self._repositories(query_variables)
        raise AssertionError(f"FakeGitHub got an unexpected document: {document[:80]}")

    # -- responses ---------------------------------------------------------

    def _rate_limit(self) -> GraphQLData:
        return {"limit": 5000, "cost": 1, "remaining": self.rate_limit.remaining, "used": 10, "resetAt": None}

    def _meta(self) -> GraphQLData:
        return {
            "organization": {
                "login": "apache",
                "databaseId": self.org_id,
                "membersWithRole": {"totalCount": len(self.members)},
                "teams": {"totalCount": len(self.teams)},
                "repositories": {"totalCount": len(self.repositories)},
            },
            "rateLimit": self._rate_limit(),
        }

    @staticmethod
    def _page(items: typing.Sequence[typing.Any], variables: typing.Mapping[str, typing.Any]) -> tuple[
        list[typing.Any], GraphQLData
    ]:
        """Slice items per first/after, and return the slice with a pageInfo.

        The cursors are just offsets into the list, which is all the scanner
        needs: it passes back whatever endCursor it was handed.
        """
        size = int(variables.get("size") or 100)
        start = int(variables.get("after") or 0)
        chunk = list(items[start : start + size])
        end = start + len(chunk)
        has_next = end < len(items)
        return chunk, {"hasNextPage": has_next, "endCursor": str(end) if has_next else None}

    def _members(self, variables: typing.Mapping[str, typing.Any]) -> GraphQLData:
        chunk, page = self._page(self.members, variables)
        return {
            "organization": {
                "membersWithRole": {
                    "totalCount": len(self.members),
                    "pageInfo": page,
                    "edges": [
                        {
                            "role": member.get("role", "MEMBER"),
                            "hasTwoFactorEnabled": member.get("two_factor", True),
                            "node": {
                                "login": member["login"],
                                "databaseId": member.get("id"),
                                "name": member.get("name"),
                            },
                        }
                        for member in chunk
                    ],
                }
            },
            "rateLimit": self._rate_limit(),
        }

    def _team_list(self, variables: typing.Mapping[str, typing.Any]) -> GraphQLData:
        chunk, page = self._page(self.teams, variables)
        return {
            "organization": {
                "teams": {
                    "totalCount": len(self.teams),
                    "pageInfo": page,
                    "nodes": [
                        {
                            "slug": team["slug"],
                            "name": team.get("name", team["slug"]),
                            "databaseId": team.get("id"),
                            "privacy": team.get("privacy", "SECRET"),
                            "members": {"totalCount": len(team.get("members", []))},
                        }
                        for team in chunk
                    ],
                }
            },
            "rateLimit": self._rate_limit(),
        }

    def _team_members(self, variables: typing.Mapping[str, typing.Any]) -> GraphQLData:
        by_slug = {team["slug"]: team for team in self.teams}
        organization: GraphQLData = {}
        index = 0
        while f"s{index}" in variables:
            slug = variables[f"s{index}"]
            team = by_slug.get(slug)
            if team is None:
                organization[f"t{index}"] = None
                index += 1
                continue
            members = list(team.get("members", []))
            chunk, page = self._page(members, {"size": variables.get("size"), "after": variables.get(f"c{index}")})
            organization[f"t{index}"] = {
                "slug": slug,
                "members": {
                    "totalCount": len(members),
                    "pageInfo": page,
                    "nodes": [{"login": login} for login in chunk],
                },
            }
            index += 1
        assert index, "TeamMembers document carried no team variables"
        return {"organization": organization, "rateLimit": self._rate_limit()}

    def _repositories(self, variables: typing.Mapping[str, typing.Any]) -> GraphQLData:
        # GitHub hands these back ordered by updatedAt descending.
        ordered = sorted(self.repositories, key=lambda repo: repo.get("updated_at", ""), reverse=True)
        chunk, page = self._page(ordered, variables)
        return {
            "organization": {
                "repositories": {
                    "totalCount": len(ordered),
                    "pageInfo": page,
                    "nodes": [
                        {
                            "name": repo["name"],
                            "databaseId": repo.get("id"),
                            "visibility": repo.get("visibility", "PUBLIC"),
                            "url": repo.get("url", "https://github.com/apache/%s" % repo["name"]),
                            "isArchived": repo.get("archived", False),
                            "updatedAt": repo.get("updated_at", "2026-01-01T00:00:00Z"),
                        }
                        for repo in chunk
                    ],
                }
            },
            "rateLimit": self._rate_limit(),
        }
