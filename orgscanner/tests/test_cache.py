"""Tests for the persistent per-organization cache"""
from __future__ import annotations

import json
import pathlib
import time
import typing

from orgscanner import cache as _cache
from orgscanner import config as _config
from orgscanner.snapshot import MemberRecord


def member_record(login: str, uid: int | None = None) -> MemberRecord:
    """A complete cached member record, as the scanner would store one."""
    return {"login": login, "id": uid, "name": None, "two_factor_enabled": True, "role": "member"}


def cache_config(tmp_path: pathlib.Path, **overrides: typing.Any) -> _config.CacheConfig:
    output = _config.OutputConfig.parse({"directory": str(tmp_path)}, base_dir=None)
    return _config.CacheConfig.parse(overrides, base_dir=None, output=output)


def test_a_missing_cache_yields_an_empty_one(tmp_path: pathlib.Path) -> None:
    store = _cache.CacheStore(cache_config(tmp_path))
    cache = store.load("apache")
    assert cache.is_empty
    assert cache.scan_serial == 0


def test_save_and_load_round_trip(tmp_path: pathlib.Path) -> None:
    store = _cache.CacheStore(cache_config(tmp_path))
    cache = store.load("apache")
    cache.organization_id = 47359
    cache.members = {"humbedooh": member_record("humbedooh", 1)}
    cache.members_total = 1
    cache.members_updated_at = time.time()
    cache.scan_serial = 4
    store.save(cache)

    reloaded = store.load("apache")
    assert reloaded.organization_id == 47359
    assert reloaded.members["humbedooh"]["id"] == 1
    assert reloaded.scan_serial == 4
    assert not reloaded.is_empty


def test_caching_can_be_disabled(tmp_path: pathlib.Path) -> None:
    store = _cache.CacheStore(cache_config(tmp_path, enabled=False))
    cache = store.load("apache")
    cache.members = {"a": member_record("a")}
    assert store.save(cache) is None
    assert store.load("apache").is_empty


def test_an_unreadable_cache_is_ignored_rather_than_fatal(tmp_path: pathlib.Path) -> None:
    config = cache_config(tmp_path)
    store = _cache.CacheStore(config)
    path = store.path_for("apache")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json")
    assert store.load("apache").is_empty


def test_a_cache_from_an_older_format_is_discarded(tmp_path: pathlib.Path) -> None:
    store = _cache.CacheStore(cache_config(tmp_path))
    path = store.path_for("apache")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 0, "members": {"a": {}}}))
    assert store.load("apache").is_empty


def test_wrongly_typed_collections_are_reset(tmp_path: pathlib.Path) -> None:
    """A hand-edited cache must not take the scanner down"""
    store = _cache.CacheStore(cache_config(tmp_path))
    path = store.path_for("apache")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": _cache.CACHE_VERSION, "members": ["not", "a", "dict"]}))
    cache = store.load("apache")
    assert cache.members == {}
    assert cache.members_total == -1


def test_organization_names_are_made_filesystem_safe(tmp_path: pathlib.Path) -> None:
    store = _cache.CacheStore(cache_config(tmp_path))
    assert "/" not in store.path_for("../../etc/passwd").name
    assert store.path_for("../../etc/passwd").parent == tmp_path / ".cache"


def test_freshness_needs_content_a_live_ttl_and_an_unchanged_total() -> None:
    cache = _cache.OrgCache(organization="apache")
    assert not cache.is_fresh("members", 3600, 10)  # Nothing cached yet

    cache.members = {"a": member_record("a")}
    cache.members_total = 10
    cache.members_updated_at = time.time()
    assert cache.is_fresh("members", 3600, 10)
    # A changed member count means something happened; refuse the cache
    assert not cache.is_fresh("members", 3600, 11)
    # A zero TTL means "never trust the cache"
    assert not cache.is_fresh("members", 0, 10)
    # ...and so does an entry older than the TTL
    cache.members_updated_at = time.time() - 7200
    assert not cache.is_fresh("members", 3600, 10)


def test_age_of_something_never_read_is_infinite() -> None:
    cache = _cache.OrgCache(organization="apache")
    assert cache.age("teams") == float("inf")


def test_the_cache_is_written_atomically(tmp_path: pathlib.Path) -> None:
    """No .tmp leftovers, so a crash cannot cost us a full rescan"""
    store = _cache.CacheStore(cache_config(tmp_path))
    cache = store.load("apache")
    cache.members = {"a": member_record("a")}
    store.save(cache)
    assert not [p for p in (tmp_path / ".cache").iterdir() if p.name.endswith(".tmp")]
