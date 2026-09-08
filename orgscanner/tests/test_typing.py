"""Type tests.

Two kinds of checking happen here. The assert_type() calls pin down what the
public API is inferred to return, so a change in the annotations shows up as a
mypy failure in this file rather than in a caller months later. The last test
runs mypy over the whole component, so the tests are also a gate on the
annotations staying correct.
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import subprocess
import sys
import typing

import pytest

import orgscanner
from orgscanner import cache as _cache
from orgscanner import config as _config
from orgscanner import ghclient, ghtypes, scanner, snapshot, writer
from orgscanner.tests.fakegithub import FakeGitHub

PACKAGE_DIR = pathlib.Path(orgscanner.__file__).resolve().parent
CHECKOUT_ROOT = PACKAGE_DIR.parent


def a_config(tmp_path: pathlib.Path) -> _config.Configuration:
    return _config.Configuration.from_dict(
        {
            "github": {"token": "x" * 40},
            "output": {"directory": str(tmp_path)},
            "scan": {"organizations": ["apache"], "team_patterns": ["*-committers"]},
        },
        base_dir=tmp_path,
    )


def test_the_package_ships_a_py_typed_marker() -> None:
    """Without it, Boxer importing orgscanner gets no type information"""
    assert (PACKAGE_DIR / "py.typed").is_file()


def test_configuration_sections_are_typed(tmp_path: pathlib.Path) -> None:
    config = a_config(tmp_path)
    typing.assert_type(config.github, _config.GitHubConfig)
    typing.assert_type(config.output.directory, pathlib.Path)
    typing.assert_type(config.output.keep_files, int)
    typing.assert_type(config.scan.organizations, "list[str]")
    typing.assert_type(config.scan.team_patterns, "list[str]")
    typing.assert_type(config.scan.matches_team("httpd-committers"), bool)
    typing.assert_type(config.performance.concurrency, int)
    typing.assert_type(config.cache.directory, "pathlib.Path | None")
    typing.assert_type(config.source, "pathlib.Path | None")


def test_load_config_accepts_both_a_string_and_a_path() -> None:
    """Operators pass strings, callers inside Boxer tend to have Paths"""
    from_string: typing.Callable[[str], _config.Configuration] = _config.load_config
    from_path: typing.Callable[[pathlib.Path], _config.Configuration] = _config.load_config
    assert from_string is _config.load_config
    assert from_path is _config.load_config


def test_snapshot_collections_are_typed(tmp_path: pathlib.Path) -> None:
    snap = snapshot.OrgSnapshot(organization="apache")
    typing.assert_type(snap.members, "list[snapshot.Member]")
    typing.assert_type(snap.teams, "list[snapshot.Team]")
    typing.assert_type(snap.repositories, "list[snapshot.Repository]")
    typing.assert_type(snap.members_by_login, "dict[str, snapshot.Member]")
    typing.assert_type(snap.teams_by_slug, "dict[str, snapshot.Team]")
    typing.assert_type(snap.organization_id, "int | None")
    typing.assert_type(snap.timestamp, "datetime.datetime | None")


def test_the_snapshot_record_types_describe_the_yaml_schema() -> None:
    """The TypedDicts and the file on disk have to stay the same shape"""
    member = snapshot.Member(login="humbedooh", id=1, two_factor_enabled=True).to_dict()
    typing.assert_type(member, snapshot.MemberRecord)
    typing.assert_type(member["login"], str)
    typing.assert_type(member["two_factor_enabled"], "bool | None")

    team = snapshot.Team(slug="httpd-committers", members=["humbedooh"]).to_dict()
    typing.assert_type(team, snapshot.TeamRecord)
    typing.assert_type(team["members"], "list[str]")

    repository = snapshot.Repository(name="httpd").to_dict()
    typing.assert_type(repository, snapshot.RepositoryRecord)
    typing.assert_type(repository["private"], bool)

    counts = snapshot.OrgSnapshot(organization="apache").counts()
    typing.assert_type(counts, snapshot.CountsRecord)
    typing.assert_type(counts["members_without_2fa"], int)


def test_2fa_status_is_a_tri_state_not_a_bool() -> None:
    """None means GitHub would not say, which is not the same as no 2FA"""
    member = snapshot.Member(login="someone")
    typing.assert_type(member.two_factor_enabled, "bool | None")
    assert member.two_factor_enabled is None
    typing.assert_type(ghtypes.as_optional_bool(None), "bool | None")
    assert ghtypes.as_optional_bool(None) is None
    assert ghtypes.as_optional_bool(False) is False


def test_the_json_coercions_return_concrete_types() -> None:
    typing.assert_type(ghtypes.as_dict(None), "dict[str, typing.Any]")
    typing.assert_type(ghtypes.as_list(None), "list[typing.Any]")
    typing.assert_type(ghtypes.as_str(None), str)
    typing.assert_type(ghtypes.as_int(None), int)
    typing.assert_type(ghtypes.as_optional_int(None), "int | None")
    typing.assert_type(ghtypes.as_optional_str(None), "str | None")
    typing.assert_type(ghtypes.as_bool(None), bool)
    typing.assert_type(ghtypes.page_info({}), ghtypes.PageInfo)
    typing.assert_type(ghtypes.page_info({}).cursor, "str | None")
    typing.assert_type(ghtypes.page_info({}).more, bool)


def test_the_cache_holds_the_same_records_as_a_snapshot() -> None:
    cache = _cache.OrgCache(organization="apache")
    typing.assert_type(cache.members, "dict[str, snapshot.MemberRecord]")
    typing.assert_type(cache.teams, "dict[str, _cache.CachedTeamRecord]")
    typing.assert_type(cache.repositories, "dict[str, snapshot.RepositoryRecord]")
    typing.assert_type(cache.age("members"), float)
    typing.assert_type(cache.is_fresh("teams", 60, 10), bool)

    stamped = _cache.cached_team(snapshot.Team(slug="httpd-committers").to_dict(), 1.0)
    typing.assert_type(stamped, _cache.CachedTeamRecord)
    typing.assert_type(stamped["refreshed_at"], float)


def test_cache_kinds_are_a_closed_set() -> None:
    """The three names have matching attributes on OrgCache; mypy holds us to them"""
    assert set(typing.get_args(_cache.CacheKind)) == {"members", "teams", "repositories"}
    cache = _cache.OrgCache(organization="apache")
    for kind in typing.get_args(_cache.CacheKind):
        assert isinstance(cache.records(kind), dict)
        assert isinstance(cache.total(kind), int)


def test_the_writer_returns_paths(tmp_path: pathlib.Path) -> None:
    config = a_config(tmp_path).output
    typing.assert_type(writer.rotate(config, "apache"), "list[pathlib.Path]")
    typing.assert_type(writer.latest_snapshot_path(config, "apache"), "pathlib.Path | None")
    typing.assert_type(
        writer.existing_snapshots(config, "apache"), "list[tuple[datetime.datetime, pathlib.Path]]"
    )
    typing.assert_type(
        writer.snapshot_filename(config, "apache", datetime.datetime.now(datetime.timezone.utc)), str
    )


def test_the_scanner_api_is_typed(tmp_path: pathlib.Path) -> None:
    instance = scanner.OrgScanner(a_config(tmp_path), client=FakeGitHub())
    typing.assert_type(instance.snapshots, "dict[str, snapshot.OrgSnapshot]")
    typing.assert_type(instance.errors, "dict[str, str]")
    typing.assert_type(instance.client, ghclient.QueryClient)
    typing.assert_type(scanner.build_team_members_query(2), str)

    async def use_it() -> None:
        typing.assert_type(await instance.scan_all(), "dict[str, snapshot.OrgSnapshot]")
        typing.assert_type(await instance.scan_organization("apache"), snapshot.OrgSnapshot)
        typing.assert_type(await scanner.scan_once(a_config(tmp_path)), "dict[str, snapshot.OrgSnapshot]")

    assert asyncio.iscoroutinefunction(use_it)


def test_the_fake_endpoint_satisfies_the_client_protocol() -> None:
    """If the fake and the real client drift apart, this stops compiling"""
    fake: ghclient.QueryClient = FakeGitHub()
    real: ghclient.QueryClient = ghclient.GraphQLClient(
        _config.Configuration.from_dict(
            {"github": {"token": "t"}, "scan": {"organizations": ["apache"]}},
        )
    )
    assert isinstance(fake, ghclient.QueryClient)
    assert isinstance(real, ghclient.QueryClient)


def test_scan_once_takes_a_configuration_or_a_path() -> None:
    """Boxer can hand it a loaded Configuration; the CLI hands it a filename"""
    from_config: typing.Callable[[_config.Configuration], typing.Any] = scanner.scan_once
    from_path: typing.Callable[[str], typing.Any] = scanner.scan_once
    assert from_config is scanner.scan_once
    assert from_path is scanner.scan_once


def test_mypy_is_happy_with_the_whole_component() -> None:
    """Run mypy in strict mode over the scanner and its tests"""
    if not _mypy_importable():
        # Boxer's own environment has no mypy; CI and the uv dev group do.
        pytest.skip("mypy is not installed in this environment")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(PACKAGE_DIR / "pyproject.toml"),
            str(PACKAGE_DIR),
        ],
        cwd=str(CHECKOUT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"mypy reported problems:\n{result.stdout}\n{result.stderr}"


def _mypy_importable() -> bool:
    """True if mypy can be run by this interpreter."""
    try:
        import mypy.api  # noqa: F401
    except ImportError:
        return False
    return True
