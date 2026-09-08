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

"""Command line front-end for the organization scanner."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import pathlib
import signal
import sys
import typing

from . import config as _config
from . import scanner as _scanner

DEFAULT_CONFIG = "orgscanner.yaml"

LOG_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orgscanner",
        description="Scan GitHub organizations for members, teams and repositories, "
        "writing one YAML snapshot per organization per scan.",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help=f"Configuration file to load (default: {DEFAULT_CONFIG} next to the scanner, or ./{DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan of every organization and exit (default is to keep scanning on scan.interval)",
    )
    parser.add_argument(
        "-o",
        "--org",
        action="append",
        dest="orgs",
        metavar="ORG",
        help="Only scan this organization; may be given more than once. Must be listed in the configuration.",
    )
    parser.add_argument("--full", action="store_true", help="Ignore the cache and do a complete scan of everything")
    parser.add_argument("--output", default=None, help="Override output.directory from the configuration file")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Scan, but do not write snapshot files (useful for a dry run or a rate limit estimate)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log at DEBUG level")
    parser.add_argument("-q", "--quiet", action="store_true", help="Log warnings and errors only")
    return parser


def find_config(explicit: str | None) -> pathlib.Path:
    """Work out which configuration file to use."""
    if explicit:
        return pathlib.Path(explicit).expanduser()
    candidates = [
        pathlib.Path.cwd() / DEFAULT_CONFIG,
        pathlib.Path(__file__).resolve().parent / DEFAULT_CONFIG,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise _config.ConfigError(
        "No configuration file given and none found at: %s" % ", ".join(str(c) for c in candidates)
    )


def setup_logging(level_name: str, verbose: bool = False, quiet: bool = False) -> None:
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    if verbose:
        level = logging.DEBUG
    if quiet:
        level = logging.WARNING
    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=LOG_DATEFMT, stream=sys.stdout)
    # aiohttp is chatty at DEBUG and has little to say that belongs in a journal.
    logging.getLogger("aiohttp").setLevel(max(level, logging.WARNING))


async def _run(args: argparse.Namespace, config: _config.Configuration) -> int:
    orgs: list[str] | None = list(args.orgs) if args.orgs else None
    if orgs:
        unknown = [org for org in orgs if org not in config.scan.organizations]
        if unknown:
            raise _config.ConfigError("Organization(s) not listed in scan.organizations: %s" % ", ".join(unknown))

    async with _scanner.OrgScanner(config) as scanner:
        if args.once:
            snapshots = await scanner.scan_all(orgs, full=args.full, write=not args.no_write)
            for org, error in scanner.errors.items():
                print(f"FAILED {org}: {error}", file=sys.stderr)
            if not snapshots:
                return 1
            return 1 if scanner.errors else 0

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signal_name in ("SIGINT", "SIGTERM"):
            with contextlib.suppress(NotImplementedError, AttributeError):
                loop.add_signal_handler(getattr(signal, signal_name), stop_event.set)
        if orgs or args.full:
            # run_forever() always scans everything configured, so honour the
            # flags for one round first and then settle into the loop.
            await scanner.scan_all(orgs, full=args.full, write=not args.no_write)
        await scanner.run_forever(stop_event)
        return 0


def main(argv: typing.Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger = logging.getLogger("orgscanner")
    try:
        config_path = find_config(args.config)
        config = _config.load_config(config_path)
    except _config.ConfigError as e:
        setup_logging("info", args.verbose, args.quiet)
        logger.error("%s", e)
        return 2

    setup_logging(config.log_level, args.verbose, args.quiet)
    if args.output:
        config.output.directory = pathlib.Path(str(args.output)).expanduser()
        if config.cache.directory is not None:
            config.cache.directory = config.output.directory / ".cache"
    logger.info(
        "Boxer organization scanner v/%s starting with %s (%d organization(s), interval %ds)",
        _scanner.VERSION,
        config_path,
        len(config.scan.organizations),
        config.scan.interval,
    )
    try:
        return asyncio.run(_run(args, config))
    except KeyboardInterrupt:
        return 0
    except _config.ConfigError as e:
        logger.error("%s", e)
        return 2
