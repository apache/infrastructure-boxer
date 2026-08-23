"""Tests for the admin user search, archive and default-branch endpoints"""
import asyncio
import types

import asfpy.messaging
import pytest

import endpoints.archive
import endpoints.defaultbranch
import endpoints.users
import plugins.configuration
import plugins.github
import plugins.projects
import plugins.session


class FakeServer:
    def __init__(self):
        self.data = plugins.configuration.InterData()
        self.config = types.SimpleNamespace(
            github=types.SimpleNamespace(org="apache", token="x" * 40)
        )


def make_session(uid="humbedooh", admin=False, logged_in=True):
    session = plugins.session.SessionObject.__new__(plugins.session.SessionObject)
    if logged_in:
        session.credentials = plugins.session.SessionCredentials(
            uid=uid, admin=admin, name="Humbe Dooh", email=f"{uid}@apache.org"
        )
    else:
        session.credentials = None
    return session


def make_person(asf_id, github_login=None, mfa=False):
    person = plugins.projects.Committer(asf_id, None)
    person.github_login = github_login
    person.github_mfa = mfa
    return person


class FakeRepo:
    def __init__(self, filename, filepath):
        self.filename = filename
        self.filepath = filepath


def stub_github_org(monkeypatch, fail=False):
    """Replaces the GitHub org with one that records PATCH calls instead of making them"""
    patched = []

    class FakeOrg:
        def __init__(self, login="", personal_access_token=""):
            self.login = login

        async def get_id(self):
            return 1

        async def api_patch(self, url, jsdata=None):
            if fail:
                raise AssertionError("GitHub said no")
            patched.append((url, jsdata))

    monkeypatch.setattr(plugins.github, "GitHubOrganisation", FakeOrg)
    return patched


def test_user_search_requires_admin_access():
    server = FakeServer()
    rv = asyncio.run(endpoints.users.process(server, make_session(), {"query": "humbedooh"}))
    assert rv["okay"] is False


def test_user_search_matches_asf_ids_and_github_logins():
    server = FakeServer()
    server.data.people = [make_person("humbedooh", "gh-humbedooh"), make_person("gstein", "gh-gstein")]
    session = make_session(admin=True)
    by_asf = asyncio.run(endpoints.users.process(server, session, {"query": "humbe"}))
    assert [x["asf_id"] for x in by_asf["results"]] == ["humbedooh"]
    by_github = asyncio.run(endpoints.users.process(server, session, {"query": "gh-gstein"}))
    assert [x["asf_id"] for x in by_github["results"]] == ["gstein"]


def test_user_search_reports_link_and_invite_status():
    server = FakeServer()
    server.data.people = [make_person("humbedooh", "gh-humbedooh", mfa=True)]
    server.data.mfa = {"gh-humbedooh": True}
    rv = asyncio.run(endpoints.users.process(server, make_session(admin=True), {"query": "humbedooh"}))
    result = rv["results"][0]
    assert result["github_id"] == "gh-humbedooh"
    assert result["github_mfa"] is True
    assert result["github_invited"] is True


def test_user_search_without_a_query_returns_nothing():
    server = FakeServer()
    server.data.people = [make_person("humbedooh", "gh-humbedooh")]
    rv = asyncio.run(endpoints.users.process(server, make_session(admin=True), {}))
    assert rv == {"okay": True, "results": []}


def test_user_search_caps_the_result_count():
    server = FakeServer()
    server.data.people = [make_person(f"user{i:02}") for i in range(20)]
    rv = asyncio.run(endpoints.users.process(server, make_session(admin=True), {"query": "user"}))
    # The break only fires after the 11th append, so the cap is 11, not 10
    assert len(rv["results"]) == 11


def test_archive_requires_admin_access(monkeypatch):
    server = FakeServer()
    rv = asyncio.run(endpoints.archive.process(server, make_session(), {"repository": "httpd"}))
    assert rv["okay"] is False


def test_archive_rejects_unknown_repositories(monkeypatch):
    server = FakeServer()
    rv = asyncio.run(
        endpoints.archive.process(server, make_session(admin=True), {"repository": "ghost"})
    )
    assert rv["okay"] is False


def test_archive_flags_the_repo_on_github_and_gitbox(monkeypatch, tmp_path):
    patched = stub_github_org(monkeypatch)
    server = FakeServer()
    repo_dir = tmp_path / "httpd.git"
    repo_dir.mkdir()
    server.data.repositories = [FakeRepo("httpd", str(repo_dir))]
    rv = asyncio.run(
        endpoints.archive.process(server, make_session(admin=True), {"repository": "httpd"})
    )
    assert rv["okay"] is True
    assert patched == [("https://api.github.com/repos/apache/httpd", {"archived": True})]
    nocommit = (repo_dir / "nocommit").read_text()
    assert "humbedooh" in nocommit


def test_archive_leaves_gitbox_alone_when_github_fails(monkeypatch, tmp_path):
    """Half-archiving would leave GitHub writable while GitBox rejects pushes, or vice versa"""
    stub_github_org(monkeypatch, fail=True)
    server = FakeServer()
    repo_dir = tmp_path / "httpd.git"
    repo_dir.mkdir()
    server.data.repositories = [FakeRepo("httpd", str(repo_dir))]
    rv = asyncio.run(
        endpoints.archive.process(server, make_session(admin=True), {"repository": "httpd"})
    )
    assert rv["okay"] is False
    assert not (repo_dir / "nocommit").exists()


def test_default_branch_requires_a_login():
    server = FakeServer()
    rv = asyncio.run(
        endpoints.defaultbranch.process(server, make_session(logged_in=False), {"default_branch": "main"})
    )
    assert rv["okay"] is False


def test_default_branch_requires_a_branch_name():
    server = FakeServer()
    rv = asyncio.run(endpoints.defaultbranch.process(server, make_session(), {"repository": "httpd"}))
    assert rv["okay"] is False


def test_default_branch_rejects_unknown_repositories():
    server = FakeServer()
    rv = asyncio.run(
        endpoints.defaultbranch.process(
            server, make_session(), {"repository": "ghost", "default_branch": "main"}
        )
    )
    assert rv["okay"] is False


def test_default_branch_updates_github_and_the_gitbox_head(monkeypatch, tmp_path):
    patched = stub_github_org(monkeypatch)
    mails = []
    monkeypatch.setattr(asfpy.messaging, "mail", lambda **kwargs: mails.append(kwargs))
    server = FakeServer()
    repo_dir = tmp_path / "httpd.git"
    repo_dir.mkdir()
    server.data.repositories = [FakeRepo("httpd", str(repo_dir))]
    rv = asyncio.run(
        endpoints.defaultbranch.process(
            server, make_session(admin=True), {"repository": "httpd", "default_branch": "main"}
        )
    )
    assert rv["okay"] is True
    assert patched == [("https://api.github.com/repos/apache/httpd", {"default_branch": "main"})]
    assert (repo_dir / "HEAD").read_text() == "ref: refs/heads/main"
    assert mails and mails[0]["recipients"] == ["private@httpd.apache.org"]
