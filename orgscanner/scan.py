#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "aiohttp>=3.9",
#   "PyYAML>=6.0.1",
# ]
# ///
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

"""Standalone launcher for the Boxer GitHub organization scanner.

The inline script metadata above lets uv provide the dependencies with no
project setup, from any working directory:

    uv run orgscanner/scan.py --config /etc/boxer/orgscanner.yaml
    ./orgscanner/scan.py --once --verbose

Inside the checkout, "uv run --project orgscanner python -m orgscanner" does the
same thing by way of orgscanner/pyproject.toml.
"""
import pathlib
import sys

# Put the checkout root on sys.path so that orgscanner resolves no matter which
# directory this was launched from.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from orgscanner.cli import main  # noqa: E402  (must follow the sys.path fix-up)

if __name__ == "__main__":
    sys.exit(main())
