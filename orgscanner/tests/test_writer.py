"""Tests for snapshot output, naming and rotation"""
from __future__ import annotations

import datetime
import pathlib
import typing

from orgscanner import config as _config
from orgscanner import writer
from orgscanner.snapshot import Member, OrgSnapshot, Repository, Team


def output_config(tmp_path: pathlib.Path, **overrides: typing.Any) -> _config.OutputConfig:
    settings: dict[str, typing.Any] = {"directory": str(tmp_path)}
    settings.update(overrides)
    return _config.OutputConfig.parse(settings, base_dir=None)


def snapshot(org: str = "apache", when: datetime.datetime | None = None) -> OrgSnapshot:
    return OrgSnapshot(
        organization=org,
        organization_id=47359,
        timestamp=when,
        team_patterns=["*-committers"],
        members=[Member(login="humbedooh", id=1, name="Daniel", two_factor_enabled=True, role="admin")],
        teams=[Team(slug="httpd-committers", name="httpd committers", id=9, privacy="secret", members=["a", "b"])],
        repositories=[
            Repository(name="httpd", id=3, visibility="public", url="https://github.com/apache/httpd"),
            Repository(name="secret-plans", id=4, visibility="private", url="https://github.com/apache/secret-plans"),
        ],
    )


def stamp(
    year: int = 2026, month: int = 9, day: int = 8, hour: int = 12, minute: int = 0, second: int = 0
) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour, minute, second, tzinfo=datetime.timezone.utc)


def test_filename_follows_the_org_timestamp_convention(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    name = writer.snapshot_filename(config, "apache", stamp())
    assert name == "apache-20260908T120000Z.yaml"


def test_naive_timestamps_are_treated_as_utc(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    naive = datetime.datetime(2026, 9, 8, 12, 0, 0)
    assert writer.snapshot_filename(config, "apache", naive) == "apache-20260908T120000Z.yaml"


def test_write_and_read_round_trips_a_snapshot(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    path = writer.write_snapshot(config, snapshot(when=stamp()))
    assert path.name == "apache-20260908T120000Z.yaml"

    restored = writer.read_snapshot(path)
    assert restored.organization == "apache"
    assert restored.organization_id == 47359
    assert [m.login for m in restored.members] == ["humbedooh"]
    assert restored.members[0].two_factor_enabled is True
    assert restored.teams[0].members == ["a", "b"]
    assert {r.name: r.visibility for r in restored.repositories} == {
        "httpd": "public",
        "secret-plans": "private",
    }


def test_the_snapshot_records_counts_for_quick_inspection(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    path = writer.write_snapshot(config, snapshot(when=stamp()))
    import yaml

    data = yaml.safe_load(path.read_text())
    assert data["counts"]["members"] == 1
    assert data["counts"]["repositories_private"] == 1
    assert data["counts"]["teams"] == 1
    assert data["team_patterns"] == ["*-committers"]


def test_only_the_last_ten_snapshots_are_kept(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    for minute in range(13):
        writer.write_snapshot(config, snapshot(when=stamp(minute=minute)))
    kept = [path.name for _when, path in writer.existing_snapshots(config, "apache")]
    assert len(kept) == 10
    # The three oldest are the ones that went
    assert kept[0] == "apache-20260908T120300Z.yaml"
    assert kept[-1] == "apache-20260908T121200Z.yaml"


def test_keep_files_is_configurable(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path, keep_files=3)
    for minute in range(6):
        writer.write_snapshot(config, snapshot(when=stamp(minute=minute)))
    assert len(writer.existing_snapshots(config, "apache")) == 3


def test_rotation_does_not_touch_another_organizations_snapshots(tmp_path: pathlib.Path) -> None:
    """Rotating 'apache' must not eat 'apache-attic' snapshots sharing the prefix"""
    config = output_config(tmp_path, keep_files=2)
    for minute in range(4):
        writer.write_snapshot(config, snapshot(org="apache", when=stamp(minute=minute)))
        writer.write_snapshot(config, snapshot(org="apache-attic", when=stamp(minute=minute)))
    assert len(writer.existing_snapshots(config, "apache")) == 2
    assert len(writer.existing_snapshots(config, "apache-attic")) == 2


def test_unrelated_yaml_files_are_left_alone(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path, keep_files=1)
    stray = tmp_path / "apache-notes.yaml"
    stray.write_text("not a snapshot\n")
    for minute in range(3):
        writer.write_snapshot(config, snapshot(when=stamp(minute=minute)))
    assert stray.exists()
    assert len(writer.existing_snapshots(config, "apache")) == 1


def test_the_latest_symlink_points_at_the_newest_snapshot(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    writer.write_snapshot(config, snapshot(when=stamp(minute=0)))
    newest = writer.write_snapshot(config, snapshot(when=stamp(minute=5)))
    link = tmp_path / "apache-latest.yaml"
    assert link.is_symlink()
    assert link.resolve() == newest.resolve()
    # It is a relative link, so the data directory can be moved wholesale
    import os

    assert not os.path.isabs(os.readlink(link))


def test_the_latest_symlink_never_counts_against_rotation(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path, keep_files=2)
    for minute in range(5):
        writer.write_snapshot(config, snapshot(when=stamp(minute=minute)))
    assert (tmp_path / "apache-latest.yaml").is_symlink()
    assert len(writer.existing_snapshots(config, "apache")) == 2


def test_the_symlink_can_be_switched_off(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path, latest_symlink=False)
    writer.write_snapshot(config, snapshot(when=stamp()))
    assert not (tmp_path / "apache-latest.yaml").exists()


def test_latest_snapshot_path_finds_the_newest(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    writer.write_snapshot(config, snapshot(when=stamp(minute=1)))
    newest = writer.write_snapshot(config, snapshot(when=stamp(minute=9)))
    assert writer.latest_snapshot_path(config, "apache") == newest
    assert writer.latest_snapshot_path(config, "nonexistent") is None


def test_no_temporary_files_are_left_behind(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path)
    writer.write_snapshot(config, snapshot(when=stamp()))
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_snapshots_are_readable_by_their_consumers(tmp_path: pathlib.Path) -> None:
    """mkstemp leaves files at 0600, and Boxer has to be able to read these"""
    import stat

    config = output_config(tmp_path)
    path = writer.write_snapshot(config, snapshot(when=stamp()))
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_the_output_directory_is_created_on_demand(tmp_path: pathlib.Path) -> None:
    config = output_config(tmp_path / "deep" / "nested")
    path = writer.write_snapshot(config, snapshot(when=stamp()))
    assert path.exists()
