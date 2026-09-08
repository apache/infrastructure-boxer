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

"""Snapshot output: writes $org-$timestamp.yaml and rotates old scans out."""
from __future__ import annotations

import datetime
import logging
import os
import pathlib
import tempfile

import yaml

from . import config as _config
from .ghtypes import as_dict
from .snapshot import OrgSnapshot

LOGGER = logging.getLogger("orgscanner.writer")

LATEST_SUFFIX = "latest"
# mkstemp() creates 0600 files, but snapshots are meant to be read by whatever
# consumes them, not just by the user the scanner runs as.
SNAPSHOT_MODE = 0o644


def snapshot_filename(config: _config.OutputConfig, organization: str, timestamp: datetime.datetime) -> str:
    """The $org-$timestamp.yaml name for one scan."""
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    stamp = timestamp.astimezone(datetime.timezone.utc).strftime(config.timestamp_format)
    return f"{organization}-{stamp}.yaml"


def existing_snapshots(
    config: _config.OutputConfig, organization: str
) -> list[tuple[datetime.datetime, pathlib.Path]]:
    """All snapshot files for one organization, oldest first.

    Only files named $org-$timestamp.yaml with a timestamp that parses are
    returned. That keeps the -latest symlink out of rotation, and stops
    organization "apache" from rotating away the snapshots of "apache-attic".
    """
    prefix = f"{organization}-"
    found: list[tuple[datetime.datetime, pathlib.Path]] = []
    try:
        entries = list(config.directory.iterdir())
    except OSError:
        return []
    for entry in entries:
        name = entry.name
        if not name.startswith(prefix) or not name.endswith(".yaml"):
            continue
        stamp = name[len(prefix) : -len(".yaml")]
        if stamp == LATEST_SUFFIX:
            continue
        try:
            when = datetime.datetime.strptime(stamp, config.timestamp_format)
        except ValueError:
            continue
        if not entry.is_file() or entry.is_symlink():
            continue
        found.append((when.replace(tzinfo=datetime.timezone.utc), entry))
    found.sort(key=lambda pair: (pair[0], pair[1].name))
    return found


def rotate(config: _config.OutputConfig, organization: str) -> list[pathlib.Path]:
    """Delete all but the newest output.keep_files snapshots, and say which."""
    snapshots = existing_snapshots(config, organization)
    excess = len(snapshots) - config.keep_files
    removed: list[pathlib.Path] = []
    if excess <= 0:
        return removed
    for _when, path in snapshots[:excess]:
        try:
            path.unlink()
            removed.append(path)
            LOGGER.info("Rotated out old snapshot %s", path.name)
        except OSError as e:
            LOGGER.warning("Could not remove old snapshot %s: %s", path, e)
    return removed


def write_snapshot(config: _config.OutputConfig, snapshot: OrgSnapshot, rotate_old: bool = True) -> pathlib.Path:
    """Write one snapshot, then rotate the older ones out."""
    timestamp = snapshot.timestamp or datetime.datetime.now(datetime.timezone.utc)
    snapshot.timestamp = timestamp
    directory = config.directory
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / snapshot_filename(config, snapshot.organization, timestamp)

    payload = yaml.safe_dump(
        snapshot.to_dict(),
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )
    # Write to a temporary file in the same directory and rename it into place,
    # so a reader never sees a partially written snapshot.
    handle, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, SNAPSHOT_MODE)
        os.replace(tmp_name, path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise

    LOGGER.info("Wrote %s (%d bytes)", path.name, len(payload))
    if config.latest_symlink:
        _update_latest_symlink(config, snapshot.organization, path)
    if rotate_old:
        rotate(config, snapshot.organization)
    return path


def read_snapshot(path: _config.PathArg) -> OrgSnapshot:
    """Read a snapshot YAML file back into an OrgSnapshot."""
    with open(path, encoding="utf-8") as f:
        return OrgSnapshot.from_dict(as_dict(yaml.safe_load(f)))


def latest_snapshot_path(config: _config.OutputConfig, organization: str) -> pathlib.Path | None:
    """The newest snapshot on disk for an organization, if there is one."""
    snapshots = existing_snapshots(config, organization)
    return snapshots[-1][1] if snapshots else None


def _update_latest_symlink(config: _config.OutputConfig, organization: str, target: pathlib.Path) -> None:
    """Point $org-latest.yaml at the snapshot we just wrote."""
    link = config.directory / f"{organization}-{LATEST_SUFFIX}.yaml"
    tmp = config.directory / f".{organization}-{LATEST_SUFFIX}.yaml.tmp"
    try:
        if tmp.exists() or tmp.is_symlink():
            tmp.unlink()
        os.symlink(target.name, tmp)  # Relative, so the data directory stays movable
        os.replace(tmp, link)
    except (OSError, NotImplementedError) as e:
        LOGGER.warning("Could not update %s: %s", link.name, e)
        try:
            if tmp.is_symlink() or tmp.exists():
                tmp.unlink()
        except OSError:
            pass
