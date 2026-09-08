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

"""Configuration handling for the organization scanner.

The scanner reads one YAML file. Every section is optional except github.token
(or one of its alternatives) and scan.organizations. The defaults below are
tuned for an organization in the 10k member and repository range.
"""
from __future__ import annotations

import dataclasses
import fnmatch
import os
import pathlib
import typing

import yaml

GRAPHQL_URL = "https://api.github.com/graphql"

# GitHub caps most connections at 100 nodes per page. Larger pages cost fewer
# rate limit points per node, but GitHub is also likelier to time out on them,
# which is why the scanner shrinks pages adaptively at runtime.
GITHUB_MAX_PAGE_SIZE = 100

DEFAULT_USER_AGENT = "ASF-Boxer-OrgScanner"

# One section of the YAML file, straight from PyYAML and not yet validated.
ConfigSection = typing.Mapping[str, typing.Any]
PathArg = typing.Union[str, "os.PathLike[str]"]

SECTIONS = ("github", "output", "scan", "performance", "cache", "logging")


class ConfigError(Exception):
    """Raised when the configuration is missing, unreadable or nonsensical."""


def _require_int(value: typing.Any, name: str, minimum: int, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        # The underlying ValueError adds nothing for someone reading a config error
        raise ConfigError(f"{name} must be an integer, got {value!r}") from None
    if number < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {number}")
    if maximum is not None and number > maximum:
        raise ConfigError(f"{name} must be at most {maximum}, got {number}")
    return number


def _require_float(value: typing.Any, name: str, minimum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"{name} must be a number, got {value!r}") from None
    if number < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {number}")
    return number


def _require_str_list(value: typing.Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):  # A single entry may be written without a list dash
        value = [value]
    if not isinstance(value, (list, tuple)):
        raise ConfigError(f"{name} must be a list of strings, got {type(value).__name__}")
    items: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise ConfigError(f"{name} must only contain non-empty strings, got {entry!r}")
        items.append(entry.strip())
    return items


def _resolve_path(path: PathArg, base_dir: pathlib.Path | None) -> pathlib.Path:
    expanded = pathlib.Path(os.path.expanduser(os.fspath(path)))
    if not expanded.is_absolute() and base_dir is not None:
        expanded = base_dir / expanded
    return expanded


@dataclasses.dataclass
class GitHubConfig:
    """GitHub credentials and endpoint."""

    token: str = ""
    graphql_url: str = GRAPHQL_URL
    user_agent: str = DEFAULT_USER_AGENT

    @classmethod
    def parse(cls, subyaml: ConfigSection, base_dir: pathlib.Path | None) -> GitHubConfig:
        token = subyaml.get("token") or ""
        if not isinstance(token, str):
            raise ConfigError("github.token must be a string")
        token_file = subyaml.get("token_file")
        token_env = subyaml.get("token_env")
        # A token file or an environment variable keeps the PAT out of a config
        # file that may be world readable or kept in a puppet repository.
        if not token and token_file:
            path = _resolve_path(str(token_file), base_dir)
            try:
                token = path.read_text(encoding="utf-8").strip()
            except OSError as e:
                raise ConfigError(f"Could not read github.token_file {path}: {e}") from e
        if not token and token_env:
            token = os.environ.get(str(token_env), "").strip()
        if not token:
            token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "No GitHub token configured. Set github.token, github.token_file, "
                "github.token_env, or the GITHUB_TOKEN environment variable."
            )
        return cls(
            token=token,
            graphql_url=str(subyaml.get("graphql_url", GRAPHQL_URL)),
            user_agent=str(subyaml.get("user_agent", DEFAULT_USER_AGENT)),
        )


@dataclasses.dataclass
class OutputConfig:
    """Where snapshots are written, and how many are kept per organization."""

    directory: pathlib.Path = pathlib.Path("./data")
    keep_files: int = 10
    timestamp_format: str = "%Y%m%dT%H%M%SZ"
    latest_symlink: bool = True

    @classmethod
    def parse(cls, subyaml: ConfigSection, base_dir: pathlib.Path | None) -> OutputConfig:
        directory = _resolve_path(str(subyaml.get("directory", "./data")), base_dir)
        timestamp_format = str(subyaml.get("timestamp_format", "%Y%m%dT%H%M%SZ"))
        if os.sep in timestamp_format or "/" in timestamp_format:
            raise ConfigError("output.timestamp_format must not contain path separators")
        return cls(
            directory=directory,
            keep_files=_require_int(subyaml.get("keep_files", 10), "output.keep_files", 1),
            timestamp_format=timestamp_format,
            latest_symlink=bool(subyaml.get("latest_symlink", True)),
        )


@dataclasses.dataclass
class ScanConfig:
    """What to scan, how often, and how deep."""

    organizations: list[str] = dataclasses.field(default_factory=list)
    team_patterns: list[str] = dataclasses.field(default_factory=list)
    interval: int = 900
    jitter: int = 0
    full_scan_every: int = 12
    organization_delay: float = 0.0

    @classmethod
    def parse(cls, subyaml: ConfigSection) -> ScanConfig:
        organizations = _require_str_list(subyaml.get("organizations"), "scan.organizations")
        if not organizations:
            raise ConfigError("scan.organizations must list at least one organization")
        duplicates = {org for org in organizations if organizations.count(org) > 1}
        if duplicates:
            raise ConfigError(f"scan.organizations contains duplicates: {', '.join(sorted(duplicates))}")
        return cls(
            organizations=organizations,
            team_patterns=_require_str_list(subyaml.get("team_patterns"), "scan.team_patterns"),
            interval=_require_int(subyaml.get("interval", 900), "scan.interval", 60),
            jitter=_require_int(subyaml.get("jitter", 0), "scan.jitter", 0),
            # 0 disables periodic full scans. The first scan against an empty
            # cache is a full one either way.
            full_scan_every=_require_int(subyaml.get("full_scan_every", 12), "scan.full_scan_every", 0),
            organization_delay=_require_float(
                subyaml.get("organization_delay", 0), "scan.organization_delay", 0
            ),
        )

    def matches_team(self, slug: str, name: str = "") -> bool:
        """True if a team slug or display name matches any configured pattern."""
        for pattern in self.team_patterns:
            if fnmatch.fnmatch(slug, pattern) or (name and fnmatch.fnmatch(name, pattern)):
                return True
        return False


@dataclasses.dataclass
class PerformanceConfig:
    """Page sizes, concurrency and rate limit safety margins.

    These are the knobs to turn when balancing how often the scanner runs
    against GitHub's budget of 5000 points per hour.
    """

    member_page_size: int = 100
    team_page_size: int = 50
    team_member_page_size: int = 100
    repository_page_size: int = 100
    team_batch_size: int = 20
    concurrency: int = 4
    min_request_interval: float = 0.0
    request_timeout: int = 60
    max_retries: int = 6
    retry_backoff: float = 2.0
    rate_limit_reserve: int = 250
    max_sleep: int = 3900
    min_page_size: int = 5

    @classmethod
    def parse(cls, subyaml: ConfigSection) -> PerformanceConfig:
        config = cls(
            member_page_size=_require_int(
                subyaml.get("member_page_size", 100), "performance.member_page_size", 1, GITHUB_MAX_PAGE_SIZE
            ),
            team_page_size=_require_int(
                subyaml.get("team_page_size", 50), "performance.team_page_size", 1, GITHUB_MAX_PAGE_SIZE
            ),
            team_member_page_size=_require_int(
                subyaml.get("team_member_page_size", 100),
                "performance.team_member_page_size",
                1,
                GITHUB_MAX_PAGE_SIZE,
            ),
            repository_page_size=_require_int(
                subyaml.get("repository_page_size", 100),
                "performance.repository_page_size",
                1,
                GITHUB_MAX_PAGE_SIZE,
            ),
            # Teams are fetched several per GraphQL document using aliases,
            # which saves thousands of round trips on a large organization.
            team_batch_size=_require_int(subyaml.get("team_batch_size", 20), "performance.team_batch_size", 1, 50),
            concurrency=_require_int(subyaml.get("concurrency", 4), "performance.concurrency", 1, 32),
            min_request_interval=_require_float(
                subyaml.get("min_request_interval", 0), "performance.min_request_interval", 0
            ),
            request_timeout=_require_int(subyaml.get("request_timeout", 60), "performance.request_timeout", 5),
            max_retries=_require_int(subyaml.get("max_retries", 6), "performance.max_retries", 0),
            retry_backoff=_require_float(subyaml.get("retry_backoff", 2.0), "performance.retry_backoff", 1.0),
            # Points left in the hourly budget below which the scanner parks
            # itself until the budget resets.
            rate_limit_reserve=_require_int(
                subyaml.get("rate_limit_reserve", 250), "performance.rate_limit_reserve", 0
            ),
            max_sleep=_require_int(subyaml.get("max_sleep", 3900), "performance.max_sleep", 1),
            min_page_size=_require_int(subyaml.get("min_page_size", 5), "performance.min_page_size", 1, 100),
        )
        smallest = min(
            config.member_page_size,
            config.team_page_size,
            config.team_member_page_size,
            config.repository_page_size,
        )
        if config.min_page_size > smallest:
            raise ConfigError(
                f"performance.min_page_size ({config.min_page_size}) must not exceed the smallest "
                f"configured page size ({smallest})"
            )
        return config


@dataclasses.dataclass
class CacheConfig:
    """Persistent cache used to avoid re-reading data that cannot have changed."""

    enabled: bool = True
    directory: pathlib.Path | None = None
    member_ttl: int = 3600
    team_ttl: int = 3600
    repository_ttl: int = 21600
    incremental_overlap: int = 300

    @classmethod
    def parse(cls, subyaml: ConfigSection, base_dir: pathlib.Path | None, output: OutputConfig) -> CacheConfig:
        directory = subyaml.get("directory")
        return cls(
            enabled=bool(subyaml.get("enabled", True)),
            # Default to a hidden directory next to the snapshots, so operators
            # only have one path to provision.
            directory=_resolve_path(str(directory), base_dir) if directory else output.directory / ".cache",
            # A cached record older than its TTL is always re-read, so staleness
            # is bounded by these values.
            member_ttl=_require_int(subyaml.get("member_ttl", 3600), "cache.member_ttl", 0),
            team_ttl=_require_int(subyaml.get("team_ttl", 3600), "cache.team_ttl", 0),
            repository_ttl=_require_int(subyaml.get("repository_ttl", 21600), "cache.repository_ttl", 0),
            # Rewind the incremental repository cutoff a little, to cover clock
            # skew between GitHub and this host.
            incremental_overlap=_require_int(
                subyaml.get("incremental_overlap", 300), "cache.incremental_overlap", 0
            ),
        )


@dataclasses.dataclass
class Configuration:
    """The complete scanner configuration."""

    github: GitHubConfig
    output: OutputConfig
    scan: ScanConfig
    performance: PerformanceConfig
    cache: CacheConfig
    log_level: str = "info"
    source: pathlib.Path | None = None

    @classmethod
    def from_dict(cls, yml: ConfigSection, base_dir: pathlib.Path | None = None) -> Configuration:
        if not isinstance(yml, dict):
            raise ConfigError("The scanner configuration must be a YAML mapping")
        unknown = set(yml) - set(SECTIONS)
        if unknown:
            raise ConfigError(f"Unknown configuration section(s): {', '.join(sorted(map(str, unknown)))}")
        output = OutputConfig.parse(_section(yml, "output"), base_dir)
        return cls(
            github=GitHubConfig.parse(_section(yml, "github"), base_dir),
            output=output,
            scan=ScanConfig.parse(_section(yml, "scan")),
            performance=PerformanceConfig.parse(_section(yml, "performance")),
            cache=CacheConfig.parse(_section(yml, "cache"), base_dir, output),
            log_level=str(_section(yml, "logging").get("level", "info")),
        )

    @classmethod
    def from_yaml(cls, path: PathArg) -> Configuration:
        config_path = pathlib.Path(os.fspath(path)).expanduser()
        try:
            with open(config_path, encoding="utf-8") as f:
                yml = yaml.safe_load(f)
        except OSError as e:
            raise ConfigError(f"Could not read configuration file {config_path}: {e}") from e
        except yaml.YAMLError as e:
            raise ConfigError(f"Could not parse configuration file {config_path}: {e}") from e
        config = cls.from_dict(yml or {}, base_dir=config_path.parent.resolve())
        config.source = config_path
        return config


def _section(yml: ConfigSection, name: str) -> ConfigSection:
    """One section of the file, as a mapping even if it was left empty."""
    section = yml.get(name)
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ConfigError(f"Configuration section {name} must be a mapping, got {type(section).__name__}")
    return typing.cast(ConfigSection, section)


def load_config(path: PathArg) -> Configuration:
    """Load and validate a scanner YAML configuration file."""
    return Configuration.from_yaml(path)
