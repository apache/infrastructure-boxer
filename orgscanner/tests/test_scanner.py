"""End-to-end tests of a scan, driven by a fake GitHub GraphQL endpoint"""
from __future__ import annotations

import asyncio
import pathlib
import time
import typing

import pytest
from orgscanner.tests.fakegithub import FakeGitHub, FakeMember, FakeRepository, FakeTeam

from orgscanner import config as _config
from orgscanner import ghclient
from orgscanner import scanner as _scanner
from orgscanner import writer
from orgscanner.ghtypes import GraphQLData
from orgscanner.snapshot import OrgSnapshot


def make_config(tmp_path: pathlib.Path, **sections: dict[str, typing.Any]) -> _config.Configuration:
    settings: dict[str, dict[str, typing.Any]] = {
        "github": {"token": "x" * 40},
        "output": {"directory": str(tmp_path)},
        "scan": {"organizations": ["apache"], "team_patterns": ["*-committers", "*-private"]},
        "performance": {"member_page_size": 10, "team_page_size": 5, "team_member_page_size": 10,
                        "repository_page_size": 10, "team_batch_size": 3, "min_page_size": 1},
        "cache": {"directory": str(tmp_path / "cache")},
    }
    for key, value in sections.items():
        settings.setdefault(key, {}).update(value)
    return _config.Configuration.from_dict(settings, base_dir=tmp_path)


def fake_org(members: int = 25, repos: int = 25, teams: int = 8) -> FakeGitHub:
    """An organization big enough to page through at the test page sizes."""
    member_records: list[FakeMember] = [
        {"login": f"user{i:03d}", "id": 1000 + i, "name": f"User {i}", "two_factor": i % 5 != 0}
        for i in range(members)
    ]
    team_records: list[FakeTeam] = [
        {
            "slug": f"proj{i}-committers",
            "name": f"proj{i} committers",
            "id": 200 + i,
            "privacy": "VISIBLE",
            "members": [f"user{j:03d}" for j in range(i + 1)],
        }
        for i in range(teams // 2)
    ]
    team_records += [
        {
            "slug": f"proj{i}-private",
            "name": f"proj{i} private",
            "id": 300 + i,
            "privacy": "SECRET",
            "members": [f"user{j:03d}" for j in range(i + 1)],
        }
        for i in range(teams // 2)
    ]
    # One team that matches no pattern, so filtering has something to exclude
    team_records += [{"slug": "infrastructure", "name": "infrastructure", "id": 1, "members": ["user000"]}]
    repository_records: list[FakeRepository] = [
        {
            "name": f"repo{i:03d}",
            "id": 500 + i,
            "visibility": "PRIVATE" if i % 4 == 0 else "PUBLIC",
            # Fixed dates in the past, so incremental cutoffs are deterministic
            "updated_at": "2020-01-%02dT00:00:00Z" % (1 + (i % 28)),
        }
        for i in range(repos)
    ]
    return FakeGitHub(members=member_records, teams=team_records, repositories=repository_records)


def scan(
    config: _config.Configuration, github: FakeGitHub, **kwargs: typing.Any
) -> tuple[OrgSnapshot, _scanner.OrgScanner]:
    """Run one scan of 'apache' against the fake endpoint."""
    scanner = _scanner.OrgScanner(config, client=github)
    return asyncio.run(scanner.scan_organization("apache", **kwargs)), scanner


def test_a_full_scan_collects_members_teams_and_repositories(tmp_path: pathlib.Path) -> None:
    github = fake_org()
    snapshot, _scanner_obj = scan(make_config(tmp_path), github)

    assert snapshot.organization == "apache"
    assert snapshot.organization_id == 47359
    assert snapshot.stats.full_scan is True

    assert len(snapshot.members) == 25
    member = snapshot.members_by_login["user007"]
    assert member.id == 1007
    assert member.name == "User 7"
    assert member.two_factor_enabled is True
    assert snapshot.members_by_login["user000"].two_factor_enabled is False
    assert snapshot.counts()["members_without_2fa"] == 5

    assert len(snapshot.repositories) == 25
    repo = {r.name: r for r in snapshot.repositories}["repo000"]
    assert repo.visibility == "private"
    assert repo.private is True
    assert repo.url == "https://github.com/apache/repo000"
    assert {r.name for r in snapshot.repositories if not r.private} == {
        f"repo{i:03d}" for i in range(25) if i % 4
    }


def test_only_teams_matching_the_patterns_are_included(tmp_path: pathlib.Path) -> None:
    github = fake_org()
    snapshot, _obj = scan(make_config(tmp_path), github)

    slugs = sorted(snapshot.teams_by_slug)
    assert slugs == [
        "proj0-committers", "proj0-private", "proj1-committers", "proj1-private",
        "proj2-committers", "proj2-private", "proj3-committers", "proj3-private",
    ]
    assert "infrastructure" not in snapshot.teams_by_slug
    assert snapshot.teams_by_slug["proj3-committers"].members == [f"user{i:03d}" for i in range(4)]
    assert snapshot.teams_by_slug["proj0-private"].privacy == "secret"
    assert snapshot.teams_by_slug["proj0-committers"].id == 200


def test_role_and_privacy_enums_are_normalised(tmp_path: pathlib.Path) -> None:
    github = FakeGitHub(
        members=[{"login": "boss", "id": 1, "role": "ADMIN"}],
        teams=[{"slug": "a-committers", "name": "a committers", "privacy": "VISIBLE", "members": ["boss"]}],
        repositories=[{"name": "r", "visibility": "INTERNAL"}],
    )
    snapshot, _obj = scan(make_config(tmp_path), github)
    assert snapshot.members[0].role == "admin"
    assert snapshot.teams[0].privacy == "visible"
    assert snapshot.repositories[0].visibility == "internal"
    assert snapshot.repositories[0].private is True  # Internal is not public


def test_every_collection_is_paginated_to_the_end(tmp_path: pathlib.Path) -> None:
    """The page sizes here are small, so nothing may be lost at a page boundary"""
    github = fake_org(members=101, repos=97, teams=20)
    snapshot, _obj = scan(make_config(tmp_path), github)
    assert len(snapshot.members) == 101
    assert len(snapshot.repositories) == 97
    assert len(snapshot.teams) == 20
    # 101 members at 10 per page is 11 requests
    assert github.request_count("members") == 11


def test_a_team_larger_than_one_page_gets_all_of_its_members(tmp_path: pathlib.Path) -> None:
    github = FakeGitHub(
        members=[{"login": f"u{i}", "id": i} for i in range(60)],
        teams=[{"slug": "big-committers", "name": "big committers", "members": [f"u{i}" for i in range(60)]}],
        repositories=[],
    )
    snapshot, _obj = scan(make_config(tmp_path), github)
    team = snapshot.teams_by_slug["big-committers"]
    assert len(team.members) == 60
    assert team.member_count == 60


def test_teams_are_batched_several_per_request(tmp_path: pathlib.Path) -> None:
    """Alias batching means the request count does not scale with the team count"""
    github = fake_org(teams=20)
    config = make_config(tmp_path, performance={"team_batch_size": 5})
    snapshot, _obj = scan(config, github)
    assert len(snapshot.teams) == 20
    # 20 matching teams at 5 per document is 4 requests, not 20
    assert github.request_count("team-members") == 4


def test_a_team_that_vanishes_mid_scan_is_dropped_not_fatal(tmp_path: pathlib.Path) -> None:
    class DropsFirstTeam(FakeGitHub):
        """A team deleted between the listing and the member fetch."""

        def _team_members(self, variables: typing.Mapping[str, typing.Any]) -> GraphQLData:
            response = super()._team_members(variables)
            response["organization"]["t0"] = None
            return response

    original = fake_org(teams=4)
    github = DropsFirstTeam(original.members, original.teams, original.repositories)
    snapshot, _obj = scan(make_config(tmp_path), github)
    assert len(snapshot.teams) < 4  # The dropped one is simply absent
    assert snapshot.teams  # ...and the rest still made it


def test_a_snapshot_file_is_written_and_rotated(tmp_path: pathlib.Path) -> None:
    github = fake_org()
    config = make_config(tmp_path)
    scanner = _scanner.OrgScanner(config, client=github)
    asyncio.run(scanner.scan_organization("apache"))
    files = writer.existing_snapshots(config.output, "apache")
    assert len(files) == 1
    restored = writer.read_snapshot(files[0][1])
    assert len(restored.members) == 25
    assert len(restored.teams) == 8


def test_write_can_be_suppressed(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path)
    scan(config, fake_org(), write=False)
    assert writer.existing_snapshots(config.output, "apache") == []


def test_a_second_scan_reuses_the_cache_and_costs_far_less(tmp_path: pathlib.Path) -> None:
    """Same results as the first scan, for a fraction of the requests"""
    config = make_config(tmp_path)
    github = fake_org()

    first = _scanner.OrgScanner(config, client=github)
    initial = asyncio.run(first.scan_organization("apache"))
    first_requests = github.requests
    assert first_requests > 5

    # A fresh scanner instance, so only the on-disk cache can help it
    github.labels.clear()
    second = _scanner.OrgScanner(config, client=github)
    again = asyncio.run(second.scan_organization("apache"))

    assert again.stats.full_scan is False
    assert sorted(again.stats.reused_from_cache) == ["members", "repositories", "teams"]
    # Only the meta probe, plus the one repository page the incremental sweep
    # reads before it recognises everything below its high-water mark
    assert github.requests - first_requests == 2
    assert github.request_count("members") == 0
    assert github.request_count("teams") == 0
    assert [m.login for m in again.members] == [m.login for m in initial.members]
    assert sorted(again.teams_by_slug) == sorted(initial.teams_by_slug)
    assert {r.name for r in again.repositories} == {r.name for r in initial.repositories}


def test_full_can_be_forced_regardless_of_the_cache(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path)
    github = fake_org()
    asyncio.run(_scanner.OrgScanner(config, client=github).scan_organization("apache"))
    baseline = github.requests
    snapshot = asyncio.run(
        _scanner.OrgScanner(config, client=github).scan_organization("apache", full=True)
    )
    assert snapshot.stats.full_scan is True
    assert snapshot.stats.reused_from_cache == []
    assert github.requests - baseline > 5


def test_a_changed_member_count_defeats_the_cache(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path)
    github = fake_org()
    asyncio.run(_scanner.OrgScanner(config, client=github).scan_organization("apache"))

    github.members.append({"login": "newbie", "id": 9999, "name": "New Bie", "two_factor": False})
    snapshot = asyncio.run(_scanner.OrgScanner(config, client=github).scan_organization("apache"))
    assert "members" not in snapshot.stats.reused_from_cache
    assert "newbie" in snapshot.members_by_login
    assert snapshot.members_by_login["newbie"].two_factor_enabled is False


def test_an_expired_member_ttl_defeats_the_cache(tmp_path: pathlib.Path) -> None:
    """2FA can flip without the member count moving, so the TTL must force a re-read"""
    config = make_config(tmp_path, cache={"member_ttl": 1})
    github = fake_org()
    scanner = _scanner.OrgScanner(config, client=github)
    asyncio.run(scanner.scan_organization("apache"))

    cache = scanner._caches["apache"]
    cache.members_updated_at = time.time() - 60  # Pretend the last read was a minute ago
    github.members[3]["two_factor"] = False
    snapshot = asyncio.run(scanner.scan_organization("apache"))
    assert "members" not in snapshot.stats.reused_from_cache
    assert snapshot.members_by_login["user003"].two_factor_enabled is False


def test_a_team_whose_size_changed_is_re_read_while_the_others_are_not(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path, cache={"team_ttl": 3600})
    github = fake_org(teams=8)
    scanner = _scanner.OrgScanner(config, client=github)
    asyncio.run(scanner.scan_organization("apache"))

    # Force team enumeration next round, but leave the per-team caches valid
    scanner._caches["apache"].teams_total = -1
    github.teams[0]["members"].append("user099")
    github.labels.clear()

    snapshot = asyncio.run(scanner.scan_organization("apache"))
    assert snapshot.stats.teams_refreshed == 1
    assert snapshot.stats.teams_from_cache == 7
    assert "user099" in snapshot.teams_by_slug["proj0-committers"].members


def test_an_incremental_repository_sweep_stops_at_the_high_water_mark(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path, scan={"full_scan_every": 0}, cache={"incremental_overlap": 0})
    github = fake_org(repos=25)
    scanner = _scanner.OrgScanner(config, client=github)
    asyncio.run(scanner.scan_organization("apache"))

    # A new repository, pushed now, replacing one that was there before: the
    # total is unchanged, so this exercises the early-stop path.
    github.repositories.pop()
    github.repositories.append(
        {"name": "brand-new", "id": 9000, "visibility": "PUBLIC", "updated_at": "2027-01-01T00:00:00Z"}
    )
    scanner._caches["apache"].repositories_updated_at = time.time() - 1
    github.labels.clear()

    snapshot = asyncio.run(scanner.scan_organization("apache"))
    names = {r.name for r in snapshot.repositories}
    assert "brand-new" in names
    # It stopped after the first page instead of walking all 25 repositories
    assert github.request_count("repositories") == 1
    assert snapshot.stats.repositories_from_cache > 0


def test_a_repository_count_mismatch_forces_the_next_scan_to_be_full(tmp_path: pathlib.Path) -> None:
    """Deletions leave no trace in an updatedAt-ordered sweep; the totals catch them"""
    config = make_config(tmp_path, scan={"full_scan_every": 0})
    github = fake_org(repos=25)
    scanner = _scanner.OrgScanner(config, client=github)
    asyncio.run(scanner.scan_organization("apache"))

    github.repositories.pop()  # Repository deleted between scans
    snapshot = asyncio.run(scanner.scan_organization("apache"))
    assert len(snapshot.repositories) == 24
    assert "repositories" not in snapshot.stats.reused_from_cache


def test_editing_the_team_patterns_invalidates_the_cached_teams(tmp_path: pathlib.Path) -> None:
    """An operator adding a pattern must see the new teams on the next scan"""
    github = fake_org(teams=8)
    first_config = make_config(tmp_path, scan={"team_patterns": ["*-committers"]})
    scanner = _scanner.OrgScanner(first_config, client=github)
    first = asyncio.run(scanner.scan_organization("apache"))
    assert all(slug.endswith("-committers") for slug in first.teams_by_slug)

    widened = make_config(tmp_path, scan={"team_patterns": ["*-committers", "*-private"]})
    again = asyncio.run(_scanner.OrgScanner(widened, client=github).scan_organization("apache"))
    assert "teams" not in again.stats.reused_from_cache
    assert len(again.teams) == 8


def test_caching_can_be_switched_off_entirely(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path, cache={"enabled": False}, scan={"full_scan_every": 12})
    github = fake_org()
    scanner = _scanner.OrgScanner(config, client=github)
    first = asyncio.run(scanner.scan_organization("apache", write=False))
    baseline = github.requests
    second = asyncio.run(scanner.scan_organization("apache", write=False))
    # Every round is a full round, and nothing is reused between them
    assert first.stats.full_scan and second.stats.full_scan
    assert second.stats.reused_from_cache == []
    assert github.requests - baseline == baseline
    assert not (tmp_path / "cache").exists()


def test_every_nth_scan_is_a_full_one(tmp_path: pathlib.Path) -> None:
    config = make_config(tmp_path, scan={"full_scan_every": 3}, cache={"member_ttl": 3600})
    github = fake_org()
    scanner = _scanner.OrgScanner(config, client=github)
    kinds = []
    for _round in range(7):
        snapshot = asyncio.run(scanner.scan_organization("apache", write=False))
        kinds.append(snapshot.stats.full_scan)
    assert kinds == [True, False, False, True, False, False, True]


def test_scan_stats_account_for_the_rate_limit_budget(tmp_path: pathlib.Path) -> None:
    github = fake_org()
    snapshot, _obj = scan(make_config(tmp_path), github)
    assert snapshot.stats.graphql_requests == github.requests
    assert snapshot.stats.graphql_points == github.points_spent
    assert snapshot.stats.rate_limit_limit == 5000
    assert snapshot.stats.rate_limit_remaining == 4990
    assert snapshot.stats.duration >= 0


def test_an_unknown_organization_is_reported_clearly(tmp_path: pathlib.Path) -> None:
    class Empty(FakeGitHub):
        def _meta(self) -> GraphQLData:
            return {"organization": None, "rateLimit": self._rate_limit()}

    with pytest.raises(Exception) as exc:
        scan(make_config(tmp_path), Empty())
    assert "no data for organization" in str(exc.value)


def test_scan_all_keeps_going_when_one_organization_fails(tmp_path: pathlib.Path) -> None:
    class Picky(FakeGitHub):
        """Refuses one organization, answers normally for the rest."""

        async def query(
            self,
            document: str,
            variables: typing.Mapping[str, typing.Any] | None = None,
            *,
            label: str = "query",
            page_size: ghclient.AdaptivePageSize | None = None,
            page_size_variable: str = "size",
        ) -> GraphQLData:
            if (variables or {}).get("org") == "broken":
                raise RuntimeError("GitHub said no")
            return await super().query(
                document, variables, label=label, page_size=page_size, page_size_variable=page_size_variable
            )

    config = make_config(tmp_path, scan={"organizations": ["broken", "apache"]})
    github = Picky(
        members=[{"login": "a", "id": 1}],
        teams=[{"slug": "x-committers", "name": "x committers", "members": ["a"]}],
        repositories=[{"name": "r"}],
    )
    scanner = _scanner.OrgScanner(config, client=github)
    results = asyncio.run(scanner.scan_all())
    assert list(results) == ["apache"]
    assert "broken" in scanner.errors
    assert "GitHub said no" in scanner.errors["broken"]


def test_the_scanner_closes_its_client_on_exit(tmp_path: pathlib.Path) -> None:
    github = fake_org()

    async def run() -> None:
        async with _scanner.OrgScanner(make_config(tmp_path), client=github) as scanner:
            await scanner.scan_organization("apache", write=False)

    asyncio.run(run())
    assert github.closed is True


def test_run_forever_stops_when_asked(tmp_path: pathlib.Path) -> None:
    github = fake_org()
    config = make_config(tmp_path, scan={"interval": 3600})

    async def run() -> None:
        scanner = _scanner.OrgScanner(config, client=github)
        stop = asyncio.Event()
        task = asyncio.create_task(scanner.run_forever(stop))
        # One round runs, then the loop parks on the interval; stopping must be
        # immediate rather than waiting out the hour.
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(run())
    assert github.request_count("meta") >= 1
    assert writer.existing_snapshots(config.output, "apache")


def test_build_team_members_query_uses_variables_not_interpolation() -> None:
    """Team slugs come from GitHub; they must never be pasted into the document"""
    document = _scanner.build_team_members_query(2)
    assert "$s0: String!" in document and "$c1: String" in document
    assert "t0: team(slug: $s0)" in document
    assert "t1: team(slug: $s1)" in document
    assert document.count("rateLimit") == 1
