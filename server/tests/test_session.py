"""Tests for cookie-based session handling"""
import asyncio
import time

from multidict import CIMultiDict

import plugins.configuration
import plugins.session


class FakeServer:
    def __init__(self):
        self.data = plugins.configuration.InterData()


class FakeRequest:
    def __init__(self, cookie=None):
        self.headers = CIMultiDict()
        if cookie is not None:
            self.headers["cookie"] = f"boxer={cookie}"


def store_session(server, session_id, uid="humbedooh", last_accessed=None):
    session = plugins.session.SessionObject(
        server,
        last_accessed=last_accessed if last_accessed is not None else int(time.time()),
        cookie=session_id,
        uid=uid,
    )
    server.data.sessions[session_id] = session
    return session


def test_no_cookie_yields_an_anonymous_session():
    server = FakeServer()
    session = asyncio.run(plugins.session.get_session(server, FakeRequest()))
    assert session.credentials is None
    assert session.cookie


def test_a_known_cookie_returns_the_stored_credentials():
    server = FakeServer()
    store_session(server, "abc-123", uid="humbedooh")
    session = asyncio.run(plugins.session.get_session(server, FakeRequest("abc-123")))
    assert session.credentials.uid == "humbedooh"


def test_an_unknown_cookie_yields_an_anonymous_session():
    server = FakeServer()
    session = asyncio.run(plugins.session.get_session(server, FakeRequest("abc-999")))
    assert session.credentials is None


def test_a_cookie_with_unexpected_characters_is_ignored():
    """Session IDs are UUIDs; anything else in the cookie must not be used as a lookup key"""
    server = FakeServer()
    store_session(server, "ABC'; DROP", uid="humbedooh")
    session = asyncio.run(plugins.session.get_session(server, FakeRequest("ABC'; DROP")))
    assert session.credentials is None


def test_stale_sessions_are_evicted():
    server = FakeServer()
    too_old = int(time.time()) - plugins.session.MAX_SESSION_AGE - 1
    store_session(server, "abc-123", last_accessed=too_old)
    session = asyncio.run(plugins.session.get_session(server, FakeRequest("abc-123")))
    assert session.credentials is None
    assert "abc-123" not in server.data.sessions


def test_a_visit_refreshes_the_session_age():
    server = FakeServer()
    stored = store_session(server, "abc-123", last_accessed=int(time.time()) - 1000)
    asyncio.run(plugins.session.get_session(server, FakeRequest("abc-123")))
    assert stored.last_accessed >= int(time.time()) - 2


def test_set_session_stores_credentials_and_returns_the_cookie():
    server = FakeServer()
    cookie = asyncio.run(plugins.session.set_session(server, uid="humbedooh", admin=True))
    assert cookie.startswith("boxer=")
    session_id = cookie.split("=", 1)[1]
    stored = server.data.sessions[session_id]
    assert stored.credentials.uid == "humbedooh"
    assert stored.credentials.admin is True
