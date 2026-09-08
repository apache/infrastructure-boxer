"""Tests for the ASF organization model: committers, projects and the GitHub link database"""
import asyncio

import asfpy.sqlite
import pytest

import plugins.ldap
import plugins.projects

# Mirrors the ids table ASF infra provisions alongside the rest of gitbox.db; Boxer never creates it
IDS_SCHEMA = """CREATE TABLE ids (
                  asfid     varchar PRIMARY KEY,
                  githubid  varchar,
                  githubnum integer,
                  mfa       integer,
                  updated   varchar
                )"""


@pytest.fixture
def linkdb(tmp_path):
    dbhandle = asfpy.sqlite.DB(str(tmp_path / "boxer.db"))
    dbhandle.runc(IDS_SCHEMA)
    return dbhandle


class FakeRepo:
    def __init__(self, filename, project, private=False):
        self.filename = filename
        self.project = project
        self.private = private


def fake_ldap(monkeypatch, members, override=None):
    """Replaces the LDAP client with one that serves canned project memberships"""

    class FakeLDAPClient:
        def __init__(self, config, **kwargs):
            self.ldap_override = override or {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get_members(self, project):
            return members.get(project, ([], []))

    monkeypatch.setattr(plugins.ldap, "LDAPClient", FakeLDAPClient)


def test_committer_without_a_link_row_has_no_github_identity(linkdb):
    committer = plugins.projects.Committer("humbedooh", linkdb)
    assert committer.github_login is None
    assert committer.github_id is None
    assert committer.github_mfa is False


def test_committer_loads_its_github_link_from_the_database(linkdb):
    linkdb.insert("ids", {"asfid": "humbedooh", "githubid": "gh-humbedooh", "githubnum": 42, "mfa": 1})
    committer = plugins.projects.Committer("humbedooh", linkdb)
    assert committer.github_login == "gh-humbedooh"
    assert committer.github_id == 42
    assert committer.github_mfa is True


def test_committer_save_roundtrip(linkdb):
    committer = plugins.projects.Committer("humbedooh", None)
    committer.github_login = "gh-humbedooh"
    committer.github_id = 42
    committer.github_mfa = True
    committer.save(linkdb)
    assert plugins.projects.Committer("humbedooh", linkdb).github_login == "gh-humbedooh"


def test_committer_save_updates_an_existing_row(linkdb):
    committer = plugins.projects.Committer("humbedooh", None)
    committer.github_login = "gh-humbedooh"
    committer.save(linkdb)
    committer.github_mfa = True
    committer.save(linkdb)
    assert plugins.projects.Committer("humbedooh", linkdb).github_mfa is True
    assert len(list(linkdb.fetch("ids", limit=None))) == 1


def test_committer_remove_deletes_the_link(linkdb):
    """Used for administrative lockouts, so the row must really be gone"""
    committer = plugins.projects.Committer("humbedooh", None)
    committer.github_login = "gh-humbedooh"
    committer.save(linkdb)
    committer.remove(linkdb)
    assert linkdb.fetchone("ids", asfid="humbedooh") is None


def test_committer_equality_matches_plain_asf_ids():
    """expire_public_optin and the endpoints rely on `asf_id in project.committers`"""
    committer = plugins.projects.Committer("humbedooh", None)
    assert committer == "humbedooh"
    assert committer != "sk"
    assert committer == plugins.projects.Committer("humbedooh", None)
    assert committer != 42
    assert "humbedooh" in [committer]
    assert hash(committer) == hash(plugins.projects.Committer("humbedooh", None))


def test_add_committer_returns_the_same_account_across_projects():
    org = plugins.projects.Organization()
    org.add_project("httpd", ["humbedooh"], [])
    org.add_project("tomcat", ["humbedooh"], [])
    assert len(org.committers) == 1
    assert {p.name for p in org.committers[0].projects} == {"httpd", "tomcat"}


def test_add_project_ignores_duplicates_and_nameless_projects():
    org = plugins.projects.Organization()
    project = org.add_project("httpd", ["humbedooh"], [])
    assert org.add_project("httpd", ["sk"], []) is None
    assert org.projects["httpd"] is project
    assert org.add_project("", ["sk"], []) is None


def test_add_repository_grants_public_repos_to_committers_and_private_to_pmc():
    org = plugins.projects.Organization()
    project = org.add_project("httpd", ["humbedooh", "sk"], ["sk"])
    public = FakeRepo("httpd-site", "httpd")
    private = FakeRepo("httpd-private", "httpd", private=True)
    project.add_repository(public, private=False)
    project.add_repository(private, private=True)
    assert project.public_repos == [public]
    assert project.private_repos == [private]
    humbedooh = org.committers[0]
    sk = [c for c in org.committers if c.asf_id == "sk"][0]
    assert humbedooh.repositories == {public}
    assert private in sk.repositories


def build_project(name, committers, pmc=()):
    org = plugins.projects.Organization()
    project = org.add_project(name, list(committers), list(pmc))
    for committer in project.committers:
        committer.github_login = f"gh-{committer.asf_id}"
        committer.github_mfa = True
    return project


def test_public_github_team_requires_mfa_from_the_live_map():
    project = build_project("httpd", ["humbedooh", "sk"])
    assert project.public_github_team({"gh-humbedooh": True, "gh-sk": False}) == ["gh-humbedooh"]


def test_public_github_team_falls_back_to_cached_mfa():
    project = build_project("httpd", ["humbedooh", "sk"])
    project.committers[1].github_mfa = False
    assert project.public_github_team() == ["gh-humbedooh"]


def test_private_github_team_only_holds_the_pmc():
    project = build_project("httpd", ["humbedooh", "sk"], pmc=["sk"])
    assert project.private_github_team() == ["gh-sk"]
    assert project.private_github_team({"gh-sk": False}) == []


def test_compile_data_groups_repositories_into_projects(monkeypatch):
    fake_ldap(monkeypatch, {"httpd": (["humbedooh", "sk"], ["sk"])})
    repos = [
        FakeRepo("httpd-site", "httpd"),
        FakeRepo("httpd-private", "httpd", private=True),
    ]
    org = asyncio.run(plugins.projects.compile_data(plugins.ldap.LDAPConfig({}), repos, None))
    project = org.projects["httpd"]
    assert [r.filename for r in project.public_repos] == ["httpd-site"]
    assert [r.filename for r in project.private_repos] == ["httpd-private"]
    assert sorted(c.asf_id for c in project.committers) == ["humbedooh", "sk"]
    assert [c.asf_id for c in project.pmc] == ["sk"]


def test_compile_data_keeps_projects_ldap_knows_nothing_about(monkeypatch):
    """An LDAP outage yields empty member lists; downstream code uses that emptiness as its
       'no LDAP data' signal, so the project must still exist with no committers"""
    fake_ldap(monkeypatch, {})
    repos = [FakeRepo("mystery", "mystery")]
    org = asyncio.run(plugins.projects.compile_data(plugins.ldap.LDAPConfig({}), repos, None))
    assert org.projects["mystery"].committers == []


def test_compile_data_skips_repos_without_a_project(monkeypatch):
    fake_ldap(monkeypatch, {})
    repos = [FakeRepo("stray", "")]
    org = asyncio.run(plugins.projects.compile_data(plugins.ldap.LDAPConfig({}), repos, None))
    assert org.projects == {}


def test_compile_data_honours_alternate_owner_overrides(monkeypatch):
    fake_ldap(
        monkeypatch,
        {"httpd": (["humbedooh"], ["humbedooh"]), "tomcat": (["sk"], ["sk"])},
        override={"repository_alternate_owners": {"httpd-site": ["tomcat"]}},
    )
    repos = [FakeRepo("httpd-site", "httpd"), FakeRepo("tomcat", "tomcat")]
    org = asyncio.run(plugins.projects.compile_data(plugins.ldap.LDAPConfig({}), repos, None))
    assert {r.filename for r in org.projects["tomcat"].public_repos} == {"tomcat", "httpd-site"}
