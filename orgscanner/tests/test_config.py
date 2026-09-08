"""Tests for the scanner's YAML configuration handling"""
import pathlib
import typing

import pytest
import yaml

from orgscanner import config as _config


def minimal(**overrides: typing.Any) -> dict[str, typing.Any]:
    """A configuration with only the required parts filled in."""
    base: dict[str, typing.Any] = {
        "github": {"token": "x" * 40},
        "scan": {"organizations": ["apache"], "team_patterns": ["*-committers"]},
    }
    base.update(overrides)
    return base


def test_minimal_configuration_fills_in_defaults() -> None:
    cfg = _config.Configuration.from_dict(minimal())
    assert cfg.output.keep_files == 10
    assert cfg.scan.interval == 900
    assert cfg.performance.member_page_size == 100
    assert cfg.cache.enabled is True


def test_a_token_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict({"scan": {"organizations": ["apache"]}})


def test_token_can_come_from_a_file(tmp_path: pathlib.Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("secret-token\n")
    cfg = _config.Configuration.from_dict(
        minimal(github={"token_file": str(token_file)}), base_dir=tmp_path
    )
    assert cfg.github.token == "secret-token"


def test_token_can_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOXER_SCANNER_TOKEN", "env-token")
    cfg = _config.Configuration.from_dict(minimal(github={"token_env": "BOXER_SCANNER_TOKEN"}))
    assert cfg.github.token == "env-token"


def test_at_least_one_organization_is_required() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict({"github": {"token": "t"}, "scan": {"organizations": []}})


def test_duplicate_organizations_are_rejected() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(
            minimal(scan={"organizations": ["apache", "apache"]})
        )


def test_a_single_pattern_may_be_written_without_a_list() -> None:
    cfg = _config.Configuration.from_dict(
        minimal(scan={"organizations": "apache", "team_patterns": "*-committers"})
    )
    assert cfg.scan.organizations == ["apache"]
    assert cfg.scan.team_patterns == ["*-committers"]


def test_unknown_sections_are_rejected_rather_than_ignored() -> None:
    """A typo'd section must not silently disable the thing it was meant to set"""
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(minimal(perfomance={"concurrency": 8}))


def test_page_sizes_are_bounded_by_githubs_maximum() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(minimal(performance={"member_page_size": 500}))


def test_min_page_size_may_not_exceed_the_configured_page_sizes() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(
            minimal(performance={"team_page_size": 10, "min_page_size": 50})
        )


def test_interval_has_a_floor() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(minimal(scan={"organizations": ["apache"], "interval": 5}))


def test_relative_paths_resolve_against_the_config_file(tmp_path: pathlib.Path) -> None:
    cfg = _config.Configuration.from_dict(minimal(output={"directory": "./data"}), base_dir=tmp_path)
    assert cfg.output.directory == tmp_path / "data"
    assert cfg.cache.directory == tmp_path / "data" / ".cache"


def test_timestamp_format_may_not_contain_path_separators() -> None:
    with pytest.raises(_config.ConfigError):
        _config.Configuration.from_dict(minimal(output={"timestamp_format": "%Y/%m/%d"}))


def test_team_patterns_are_fnmatched_against_slug_and_name() -> None:
    cfg = _config.Configuration.from_dict(
        minimal(scan={"organizations": ["apache"], "team_patterns": ["*-committers", "*-private"]})
    )
    assert cfg.scan.matches_team("httpd-committers", "httpd committers")
    assert cfg.scan.matches_team("empire-db-private", "empire-db private")
    assert not cfg.scan.matches_team("infrastructure", "infrastructure")
    # A team whose slug does not match but whose display name does still counts
    assert cfg.scan.matches_team("weird-slug", "solr-committers")


def test_no_patterns_means_no_teams_match() -> None:
    cfg = _config.Configuration.from_dict(minimal(scan={"organizations": ["apache"]}))
    assert cfg.scan.team_patterns == []
    assert not cfg.scan.matches_team("httpd-committers", "httpd committers")


def test_the_shipped_sample_configuration_is_valid() -> None:
    sample = pathlib.Path(__file__).resolve().parent.parent / "orgscanner.yaml"
    cfg = _config.Configuration.from_yaml(sample)
    assert cfg.scan.organizations
    assert cfg.output.keep_files == 10
    # ...and it must stay parseable as plain YAML for operators to copy
    assert isinstance(yaml.safe_load(sample.read_text()), dict)
