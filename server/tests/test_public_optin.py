"""Tests for the team listing opt-in and the $project-public GitHub teams it drives"""
import asyncio
import json

import asfpy.sqlite
import pytest

import endpoints.optin
import endpoints.preferences
import plugins.background
import plugins.configuration
import plugins.github
import plugins.projects
import plugins.session

# ASF infra provisions this alongside the rest of gitbox.db; Boxer never creates it
PUBLIC_OPTIN_SCHEMA = """CREATE TABLE publicoptin (
                           asfid    varchar,
                           project  varchar,
                           updated  varchar,
                           PRIMARY KEY (asfid, project)
                         )"""


class FakeRepo:
    """Stand-in for plugins.repositories.Repository, which needs a real git dir on disk"""

    def __init__(self, filename):
        self.filename = filename
        self.private = False


class FakeDatabase:
    def __init__(self, client):
        self.client = client


class FakeServer:
    def __init__(self, client):
        self.data = plugins.configuration.InterData()
        self.database = FakeDatabase(client)


@pytest.fixture
def db(tmp_path):
    dbhandle = asfpy.sqlite.DB(str(tmp_path / "boxer.db"))
    dbhandle.runc(PUBLIC_OPTIN_SCHEMA)
    return dbhandle


def build_project(name, committers, pmc=(), public=True):
    """Builds a single-project Organization with every committer linked and MFA enabled"""
    org = plugins.projects.Organization()
    project = org.add_project(name, list(committers), list(pmc))
    for committer in project.committers:
        committer.github_login = f"gh-{committer.asf_id}"
        committer.github_mfa = True
    if public:
        project.public_repos.append(FakeRepo(name))
    return org, project


def team_node(slug, name, members=()):
    return {
        "node": {
            "databaseId": 1234,
            "slug": slug,
            "name": name,
            "members": {"edges": [{"node": {"login": x}} for x in members]},
            "repositories": {"edges": []},
        },
    }


def test_optin_roundtrip(db):
    assert plugins.projects.load_public_optin(db) == {}
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd", "tomcat"])
    plugins.projects.save_public_optin(db, "sk", {"httpd"}, ["httpd"])
    assert plugins.projects.load_public_optin(db) == {
        "humbedooh": {"httpd", "tomcat"},
        "sk": {"httpd"},
    }


def test_save_replaces_the_selection_within_scope(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd", "tomcat"])
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["tomcat"])
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"tomcat"}}


def test_save_leaves_optins_outside_the_scope_alone(db):
    """A project the page could not render must not be silently opted out of"""
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd", "tomcat"])
    # tomcat has dropped out of the offered set this round; saving httpd off must not touch it
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, [])
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"tomcat"}}


def test_save_empty_selection_clears_the_whole_scope(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd", "tomcat"])
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, [])
    assert plugins.projects.load_public_optin(db) == {}


def test_save_is_per_person(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    plugins.projects.save_public_optin(db, "sk", {"httpd"}, ["httpd"])
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, [])
    assert plugins.projects.load_public_optin(db) == {"sk": {"httpd"}}


def test_save_does_not_rewrite_unchanged_rows(db):
    """Re-saving an identical selection must be a no-op, so a later failure cannot lose it"""
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd"])
    before = db.fetchone("publicoptin", asfid="humbedooh", project="httpd")["updated"]
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd", "tomcat"}, ["httpd"])
    assert db.fetchone("publicoptin", asfid="humbedooh", project="httpd")["updated"] == before


def test_expire_drops_optins_for_former_committers(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    _, project = build_project("httpd", ["sk"])  # humbedooh has left
    optin = plugins.projects.load_public_optin(db)
    plugins.projects.expire_public_optin(db, {"httpd": project}, optin)
    assert plugins.projects.load_public_optin(db) == {}
    assert optin == {"humbedooh": set()}  # in-memory map updated too


def test_expire_keeps_optins_for_current_committers(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    _, project = build_project("httpd", ["humbedooh", "sk"])
    plugins.projects.expire_public_optin(db, {"httpd": project}, plugins.projects.load_public_optin(db))
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"httpd"}}


def test_expire_skips_projects_with_no_ldap_data(db):
    """An LDAP outage leaves committers empty; that must not be read as 'everyone left'"""
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    _, project = build_project("httpd", [])
    plugins.projects.expire_public_optin(db, {"httpd": project}, plugins.projects.load_public_optin(db))
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"httpd"}}


def test_expire_skips_projects_it_knows_nothing_about(db):
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    plugins.projects.expire_public_optin(db, {}, plugins.projects.load_public_optin(db))
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"httpd"}}


def test_expire_prevents_silent_republish_on_rejoin(db):
    """Leaving then rejoining a project must require opting in again"""
    plugins.projects.save_public_optin(db, "humbedooh", {"httpd"}, ["httpd"])
    _, gone = build_project("httpd", ["sk"])
    plugins.projects.expire_public_optin(db, {"httpd": gone}, plugins.projects.load_public_optin(db))
    _, back = build_project("httpd", ["humbedooh", "sk"])
    assert back.public_optin_github_team(plugins.projects.load_public_optin(db)) == []


def test_public_optin_github_team_only_holds_people_who_opted_in():
    _, project = build_project("httpd", ["humbedooh", "sk", "gstein"])
    opted_in = {"humbedooh": {"httpd"}, "gstein": {"httpd"}}
    assert sorted(project.public_optin_github_team(opted_in)) == ["gh-gstein", "gh-humbedooh"]


def test_public_optin_github_team_ignores_optins_for_other_projects():
    _, project = build_project("httpd", ["humbedooh"])
    assert project.public_optin_github_team({"humbedooh": {"tomcat"}}) == []


def test_public_optin_github_team_requires_mfa():
    _, project = build_project("httpd", ["humbedooh", "sk"])
    opted_in = {"humbedooh": {"httpd"}, "sk": {"httpd"}}
    mfa = {"gh-humbedooh": True, "gh-sk": False}
    assert project.public_optin_github_team(opted_in, mfa) == ["gh-humbedooh"]


def test_public_optin_github_team_falls_back_to_cached_mfa():
    _, project = build_project("httpd", ["humbedooh", "sk"])
    for committer in project.committers:
        committer.github_mfa = committer.asf_id == "humbedooh"
    opted_in = {"humbedooh": {"httpd"}, "sk": {"httpd"}}
    assert project.public_optin_github_team(opted_in) == ["gh-humbedooh"]


def test_public_optin_does_not_leak_into_the_committers_team():
    _, project = build_project("httpd", ["humbedooh", "sk"])
    assert sorted(project.public_github_team()) == ["gh-humbedooh", "gh-sk"]
    assert project.public_optin_github_team({}) == []


def make_org_with_stubbed_post(monkeypatch):
    org = plugins.github.GitHubOrganisation(login="apache", personal_access_token="x" * 40)
    org.orgid = 1
    posted = []

    async def fake_post(url, jsdata=None):
        posted.append(jsdata)
        return json.dumps({"id": 4321})

    monkeypatch.setattr(org, "api_post", fake_post)
    return org, posted


def test_setup_teams_creates_a_public_team_when_someone_opted_in(monkeypatch):
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"])
    asyncio.run(org.setup_teams({"httpd": project}, {"humbedooh": {"httpd"}}, {"gh-humbedooh": True}))
    assert {"httpd committers", "httpd public"} == {x["name"] for x in posted}
    public = [x for x in org.teams if x.type == "public"]
    assert len(public) == 1
    assert public[0].slug == "httpd-public"


def test_setup_teams_makes_the_public_team_org_visible(monkeypatch):
    """'closed' is required so the team can be named as a deployment environment approver"""
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"])
    asyncio.run(org.setup_teams({"httpd": project}, {"humbedooh": {"httpd"}}, {"gh-humbedooh": True}))
    privacy = {x["name"]: x["privacy"] for x in posted}
    assert privacy["httpd public"] == "closed"
    assert privacy["httpd committers"] == "secret"


def test_setup_teams_skips_the_public_team_when_nobody_opted_in(monkeypatch):
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"])
    asyncio.run(org.setup_teams({"httpd": project}, {}, {"gh-humbedooh": True}))
    assert [x["name"] for x in posted] == ["httpd committers"]


def test_setup_teams_skips_the_public_team_when_the_opted_in_user_lacks_mfa(monkeypatch):
    """Otherwise we create a visible team that adjust_teams can never put anyone into"""
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"])
    asyncio.run(org.setup_teams({"httpd": project}, {"humbedooh": {"httpd"}}, {"gh-humbedooh": False}))
    assert [x["name"] for x in posted] == ["httpd committers"]


def test_setup_teams_skips_the_public_team_for_projects_without_public_repos(monkeypatch):
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"], public=False)
    asyncio.run(org.setup_teams({"httpd": project}, {"humbedooh": {"httpd"}}, {"gh-humbedooh": True}))
    assert posted == []


def test_setup_teams_does_not_recreate_an_existing_public_team(monkeypatch):
    org, posted = make_org_with_stubbed_post(monkeypatch)
    _, project = build_project("httpd", ["humbedooh"])
    org.teams = [
        plugins.github.GitHubTeam(org, team_node("httpd-committers", "httpd committers")),
        plugins.github.GitHubTeam(org, team_node("httpd-public", "httpd public")),
    ]
    asyncio.run(org.setup_teams({"httpd": project}, {"humbedooh": {"httpd"}}, {"gh-humbedooh": True}))
    assert posted == []


def make_server_with_teams(monkeypatch, nodes, public=True):
    """Builds an httpd project plus the GitHub teams named in nodes, recording all membership calls"""
    org = plugins.github.GitHubOrganisation(login="apache", personal_access_token="x" * 40)
    org.orgid = 1
    added: list = []
    removed: list = []
    _, project = build_project("httpd", ["humbedooh", "sk"], pmc=["sk"], public=public)
    server = FakeServer(None)
    server.data.projects = {"httpd": project}
    server.data.teams = []
    server.data.mfa = {"gh-humbedooh": True, "gh-sk": True}
    for slug, name, members in nodes:
        team = plugins.github.GitHubTeam(org, team_node(slug, name, members))

        async def add(github_id, slug=slug):
            added.append((slug, github_id))

        async def remove(github_id, slug=slug):
            removed.append((slug, github_id))

        monkeypatch.setattr(team, "add_member", add)
        monkeypatch.setattr(team, "remove_member", remove)
        server.data.teams.append(team)
    return server, added, removed


def test_adjust_teams_adds_and_removes_public_team_members(monkeypatch):
    server, added, removed = make_server_with_teams(
        monkeypatch, [("httpd-public", "httpd public", ["gh-sk", "gh-stranger"])]
    )
    server.data.public_optin = {"humbedooh": {"httpd"}}
    asyncio.run(plugins.background.adjust_teams(server))
    assert added == [("httpd-public", "gh-humbedooh")]
    assert sorted(removed) == [("httpd-public", "gh-sk"), ("httpd-public", "gh-stranger")]


def test_adjust_teams_empties_a_public_team_when_everyone_opts_out(monkeypatch):
    server, added, removed = make_server_with_teams(
        monkeypatch, [("httpd-public", "httpd public", ["gh-humbedooh"])]
    )
    server.data.public_optin = {}
    asyncio.run(plugins.background.adjust_teams(server))
    assert added == []
    assert removed == [("httpd-public", "gh-humbedooh")]


def test_adjust_teams_honours_opt_out_even_without_public_repos(monkeypatch):
    """A project losing its public repos must not strand someone in a visible team"""
    server, added, removed = make_server_with_teams(
        monkeypatch, [("httpd-public", "httpd public", ["gh-humbedooh"])], public=False
    )
    server.data.public_optin = {}
    asyncio.run(plugins.background.adjust_teams(server))
    assert removed == [("httpd-public", "gh-humbedooh")]


def test_adjust_teams_leaves_public_team_alone_when_ldap_is_down(monkeypatch):
    server, added, removed = make_server_with_teams(
        monkeypatch, [("httpd-public", "httpd public", ["gh-humbedooh"])]
    )
    server.data.public_optin = {"humbedooh": {"httpd"}}
    server.data.projects["httpd"].committers = []  # what compile_data leaves behind on an LDAP failure
    asyncio.run(plugins.background.adjust_teams(server))
    assert added == [] and removed == []


def test_adjust_teams_keeps_the_committers_team_independent_of_the_opt_in(monkeypatch):
    server, added, removed = make_server_with_teams(
        monkeypatch,
        [
            ("httpd-committers", "httpd committers", []),
            ("httpd-public", "httpd public", []),
        ],
    )
    server.data.public_optin = {"humbedooh": {"httpd"}}
    asyncio.run(plugins.background.adjust_teams(server))
    assert sorted(added) == [
        ("httpd-committers", "gh-humbedooh"),
        ("httpd-committers", "gh-sk"),
        ("httpd-public", "gh-humbedooh"),
    ]
    assert removed == []


def make_optin_server(db, uid="humbedooh", projects=("httpd", "tomcat"), repoless=()):
    server = FakeServer(db)
    org = plugins.projects.Organization()
    for name in list(projects) + list(repoless):
        project = org.add_project(name, [uid], [uid])
        if name not in repoless:
            project.public_repos.append(FakeRepo(name))
    person = org.add_committer(uid)
    server.data.people = [person]
    server.data.projects = org.projects
    session = plugins.session.SessionObject.__new__(plugins.session.SessionObject)
    session.credentials = plugins.session.SessionCredentials(uid=uid)
    return server, session


def test_optin_endpoint_saves_the_selection(db):
    server, session = make_optin_server(db)
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd"]}))
    assert rv["okay"] is True
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"httpd"}}
    assert server.data.public_optin == {"humbedooh": {"httpd"}}


def test_optin_endpoint_clears_the_selection(db):
    server, session = make_optin_server(db)
    asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd", "tomcat"]}))
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": []}))
    assert rv["okay"] is True
    assert plugins.projects.load_public_optin(db) == {}


def test_optin_endpoint_preserves_optins_it_did_not_offer(db):
    """solr is absent from this round's project data, so a save must leave its opt-in intact"""
    plugins.projects.save_public_optin(db, "humbedooh", {"solr"}, ["solr"])
    server, session = make_optin_server(db)
    server.data.public_optin = plugins.projects.load_public_optin(db)
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd"]}))
    assert rv["okay"] is True
    assert plugins.projects.load_public_optin(db) == {"humbedooh": {"httpd", "solr"}}
    assert server.data.public_optin == {"humbedooh": {"httpd", "solr"}}


def test_optin_endpoint_rejects_projects_the_user_is_not_on(db):
    server, session = make_optin_server(db)
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd", "solr"]}))
    assert rv["okay"] is False
    assert "solr" in rv["message"]
    assert plugins.projects.load_public_optin(db) == {}


def test_optin_endpoint_rejects_projects_with_no_public_repos(db):
    """No public repos means setup_teams would never create the team, so accepting would be a lie"""
    server, session = make_optin_server(db, projects=("httpd",), repoless=("incubator",))
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["incubator"]}))
    assert rv["okay"] is False
    assert "incubator" in rv["message"]
    assert plugins.projects.load_public_optin(db) == {}


def test_optin_endpoint_rejects_a_malformed_payload(db):
    server, session = make_optin_server(db)
    for payload in ({}, {"projects": "httpd"}, {"projects": ["httpd", 5]}, {"projects": None}):
        rv = asyncio.run(endpoints.optin.process(server, session, payload))
        assert rv["okay"] is False, payload
    assert plugins.projects.load_public_optin(db) == {}


def test_optin_endpoint_requires_a_login(db):
    server, session = make_optin_server(db)
    session.credentials = None
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd"]}))
    assert rv["okay"] is False
    assert plugins.projects.load_public_optin(db) == {}


def test_optin_endpoint_handles_an_unknown_account(db):
    server, session = make_optin_server(db)
    server.data.people = []
    rv = asyncio.run(endpoints.optin.process(server, session, {"projects": ["httpd"]}))
    assert rv["okay"] is False
    assert plugins.projects.load_public_optin(db) == {}


def test_preferences_offers_the_projects_the_user_commits_to(db):
    server, session = make_optin_server(db)
    prefs = asyncio.run(endpoints.preferences.process(server, session, {}))
    assert prefs["projects"] == ["httpd", "tomcat"]
    assert prefs["public_optin"] == []


def test_preferences_does_not_offer_projects_without_public_repos(db):
    server, session = make_optin_server(db, projects=("httpd",), repoless=("incubator",))
    prefs = asyncio.run(endpoints.preferences.process(server, session, {}))
    assert prefs["projects"] == ["httpd"]


def test_preferences_reports_the_current_optin(db):
    server, session = make_optin_server(db)
    asyncio.run(endpoints.optin.process(server, session, {"projects": ["tomcat"]}))
    prefs = asyncio.run(endpoints.preferences.process(server, session, {}))
    assert prefs["public_optin"] == ["tomcat"]


def test_preferences_does_not_leak_anyone_elses_optin(db):
    server, session = make_optin_server(db)
    server.data.public_optin = {"sk": {"httpd"}}
    prefs = asyncio.run(endpoints.preferences.process(server, session, {}))
    assert prefs["public_optin"] == []


def test_preferences_is_safe_when_logged_out(db):
    server, session = make_optin_server(db)
    session.credentials = None
    prefs = asyncio.run(endpoints.preferences.process(server, session, {}))
    assert prefs["projects"] == []
    assert prefs["public_optin"] == []
