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

"""Helpers for turning GitHub's JSON into typed Python values.

A GraphQL response arrives as parsed JSON, so every field in it is Any until
something looks at it. GitHub also returns nulls in places where its schema
suggests it will not: a suspended account inside a member connection, or a team
that was deleted while we were paging through the organization. The scanner
therefore reads every field through one of the coercions below, which keeps the
guesswork at the edge of the program and lets mypy check the rest.
"""
from __future__ import annotations

import typing

# A decoded GraphQL response body, or any JSON object nested inside one.
GraphQLData = dict[str, typing.Any]


def as_dict(value: object) -> GraphQLData:
    """Return value if it is a JSON object, otherwise an empty one."""
    if isinstance(value, dict):
        return typing.cast(GraphQLData, value)
    return {}


def as_list(value: object) -> list[typing.Any]:
    """Return value if it is a JSON array, otherwise an empty one."""
    if isinstance(value, list):
        return value
    return []


def as_str(value: object, default: str = "") -> str:
    """Return value as a string, or default if it is missing or null."""
    if isinstance(value, str) and value:
        return value
    return default


def as_optional_str(value: object) -> str | None:
    """Return value as a string, or None if it is missing, null or empty."""
    if isinstance(value, str) and value:
        return value
    return None


def as_int(value: object, default: int = 0) -> int:
    """Return value as an int, or default if it is missing or not a number."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def as_optional_int(value: object) -> int | None:
    """Return value as an int, or None if it is missing or not a number."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def as_bool(value: object) -> bool:
    """Return value as a bool, treating anything missing as False."""
    return bool(value)


def as_optional_bool(value: object) -> bool | None:
    """Return value as a bool, or None if GitHub would not tell us.

    2FA status is the field this matters for: GitHub only reports it to
    organization owners, and a null there means "not allowed to know", which is
    a different answer from "no 2FA".
    """
    if value is None:
        return None
    return bool(value)


def child(value: object, *keys: str) -> GraphQLData:
    """Walk into nested JSON objects, returning {} as soon as one is missing.

    So child(data, "organization", "teams") gets at data["organization"]["teams"]
    without a chain of `or {}` at every step.
    """
    current = as_dict(value)
    for key in keys:
        current = as_dict(current.get(key))
    return current


class PageInfo(typing.NamedTuple):
    """How far through a paginated connection we are."""

    has_next: bool
    cursor: str | None

    @property
    def more(self) -> bool:
        """True when there is another page worth asking for.

        GitHub occasionally sets hasNextPage while leaving endCursor null, and a
        request with a null cursor starts again from the beginning. Boxer's own
        loaders distrust the flag for that reason, so a page only counts as
        continuable if there is a cursor to continue from.
        """
        return bool(self.has_next and self.cursor)


def page_info(connection: GraphQLData) -> PageInfo:
    """Read the pageInfo out of a connection."""
    info = as_dict(connection.get("pageInfo"))
    return PageInfo(has_next=as_bool(info.get("hasNextPage")), cursor=as_optional_str(info.get("endCursor")))
