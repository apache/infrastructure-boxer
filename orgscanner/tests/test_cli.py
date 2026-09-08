"""Tests for the standalone command line front-end"""
from __future__ import annotations

import argparse
import pathlib
import typing

import pytest

from orgscanner import cli
from orgscanner import config as _config

SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "orgscanner.yaml"


def test_defaults_are_a_looping_scan_of_everything() -> None:
    args = cli.build_parser().parse_args([])
    assert args.once is False
    assert args.full is False
    assert args.orgs is None


def test_organizations_can_be_narrowed_and_repeated() -> None:
    args = cli.build_parser().parse_args(["-o", "apache", "--org", "apachetest", "--once"])
    assert args.orgs == ["apache", "apachetest"]
    assert args.once is True


def test_an_explicit_config_path_wins() -> None:
    assert cli.find_config(str(SAMPLE)) == SAMPLE


def test_the_shipped_config_is_found_next_to_the_scanner(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)  # Nothing to find in the working directory
    assert cli.find_config(None) == SAMPLE


def test_a_config_in_the_working_directory_takes_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    local = tmp_path / "orgscanner.yaml"
    local.write_text("github: {token: t}\nscan: {organizations: [apache]}\n")
    monkeypatch.chdir(tmp_path)
    assert cli.find_config(None) == local


def test_a_missing_config_is_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "DEFAULT_CONFIG", "no-such-file.yaml")
    with pytest.raises(_config.ConfigError):
        cli.find_config(None)


def test_a_broken_config_exits_with_a_status_rather_than_a_traceback(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("scan: {organizations: []}\n")
    assert cli.main(["--config", str(bad), "--once"]) == 2


def test_an_unknown_organization_on_the_command_line_is_refused(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "cfg.yaml"
    config.write_text(
        "github: {token: t}\nscan: {organizations: [apache]}\noutput: {directory: %s}\n" % tmp_path
    )
    assert cli.main(["--config", str(config), "--once", "--org", "nope"]) == 2


def test_the_output_directory_can_be_overridden(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "cfg.yaml"
    config.write_text("github: {token: t}\nscan: {organizations: [apache]}\n")
    seen: dict[str, pathlib.Path | None] = {}

    async def fake_run(args: argparse.Namespace, configuration: typing.Any) -> int:
        seen["output"] = configuration.output.directory
        seen["cache"] = configuration.cache.directory
        return 0

    monkeypatch.setattr(cli, "_run", fake_run)
    assert cli.main(["--config", str(config), "--once", "--output", str(tmp_path / "elsewhere")]) == 0
    assert seen["output"] == tmp_path / "elsewhere"
    # The cache follows the output directory rather than pointing at the old one
    assert seen["cache"] == tmp_path / "elsewhere" / ".cache"
