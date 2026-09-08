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

"""ASF Infrastructure Boxer, GitHub organization scanner.

Scans GitHub organizations for their members (with 2FA status), the teams
matching a set of configured patterns, and their repositories, then writes one
YAML snapshot per organization per scan.

Standalone:

    uv run orgscanner/scan.py --config orgscanner/orgscanner.yaml

As a background task inside Boxer:

    import orgscanner

    scanner = orgscanner.OrgScanner(orgscanner.load_config("orgscanner.yaml"))
    asyncio.create_task(scanner.run_forever())

Or one scan at a time, from a task Boxer already has running:

    snapshots = await orgscanner.scan_once("orgscanner.yaml")
"""
from .cache import CachedTeamRecord, CacheKind, CacheStore, OrgCache
from .config import (
    CacheConfig,
    ConfigError,
    Configuration,
    GitHubConfig,
    OutputConfig,
    PathArg,
    PerformanceConfig,
    ScanConfig,
    load_config,
)
from .ghclient import AdaptivePageSize, GitHubError, GitHubQueryError, GraphQLClient, QueryClient, RateLimit
from .scanner import VERSION, OrgScanner, run_forever, scan_once
from .snapshot import (
    CountsRecord,
    Member,
    MemberRecord,
    OrgSnapshot,
    Repository,
    RepositoryRecord,
    ScanRecord,
    ScanStats,
    SnapshotRecord,
    Team,
    TeamRecord,
)
from .writer import latest_snapshot_path, read_snapshot, rotate, write_snapshot

__version__ = VERSION

__all__ = [
    "VERSION",
    "AdaptivePageSize",
    "CacheConfig",
    "CacheKind",
    "CacheStore",
    "CachedTeamRecord",
    "ConfigError",
    "Configuration",
    "CountsRecord",
    "GitHubConfig",
    "GitHubError",
    "GitHubQueryError",
    "GraphQLClient",
    "Member",
    "MemberRecord",
    "OrgCache",
    "OrgScanner",
    "OrgSnapshot",
    "OutputConfig",
    "PathArg",
    "PerformanceConfig",
    "QueryClient",
    "RateLimit",
    "Repository",
    "RepositoryRecord",
    "ScanConfig",
    "ScanRecord",
    "ScanStats",
    "SnapshotRecord",
    "Team",
    "TeamRecord",
    "__version__",
    "latest_snapshot_path",
    "load_config",
    "read_snapshot",
    "rotate",
    "run_forever",
    "scan_once",
    "write_snapshot",
]
