"""Tests for the background synchronisation of teams and repositories"""
import asyncio

import plugins.background
import plugins.configuration
import plugins.github
import plugins.projects


class FakeRepo:
    def __init__(self, filename, private=False):
        self.filename = filename
        self.private = private


class FakeServer:
    def __init__(self):
        self.data = plugins.configuration.InterData()


def team_node(slug, name, members=(), repos=()):
    return {
        "node": {
            "databaseId": 1234,
            "slug": slug,
            "name": name,
            "members": {"edges": [{"node": {"login": x}} for x in members]},
            "repositories": {"edges": [{"node": {"name": x}} for x in repos]},
        },
    }


def make_server(monkeypatch, nodes):
    """Builds an httpd project plus the GitHub teams named in nodes, recording all sync calls"""
    org = plugins.github.GitHubOrganisation(login="apache", personal_access_token="x" * 40)
    org.orgid = 1
    asf_org = plugins.projects.Organization()
    project = asf_org.add_project("httpd", ["humbedooh"], ["humbedooh"])
    for committer in project.committers:
        committer.github_login = f"gh-{committer.asf_id}"
        committer.github_mfa = True
    server = FakeServer()
    server.data.projects = {"httpd": project}
    server.data.mfa = {"gh-humbedooh": True}
    calls = {"added": [], "removed": [], "repo_added": [], "repo_removed": []}
    for slug, name, members, repos in nodes:
        team = plugins.github.GitHubTeam(org, team_node(slug, name, members, repos))

        async def add_member(github_id, slug=slug):
            calls["added"].append((slug, github_id))

        async def remove_member(github_id, slug=slug):
            calls["removed"].append((slug, github_id))

        async def add_repository(reponame, slug=slug):
            calls["repo_added"].append((slug, reponame))

        async def remove_repository(reponame, slug=slug):
            calls["repo_removed"].append((slug, reponame))

        monkeypatch.setattr(team, "add_member", add_member)
        monkeypatch.setattr(team, "remove_member", remove_member)
        monkeypatch.setattr(team, "add_repository", add_repository)
        monkeypatch.setattr(team, "remove_repository", remove_repository)
        server.data.teams.append(team)
    return server, calls


def test_adjust_teams_fills_the_private_team_from_the_pmc(monkeypatch):
    server, calls = make_server(monkeypatch, [("httpd-private", "httpd private", ["gh-stranger"], [])])
    server.data.projects["httpd"].private_repos.append(FakeRepo("httpd-private", True))
    asyncio.run(plugins.background.adjust_teams(server))
    assert calls["added"] == [("httpd-private", "gh-humbedooh")]
    assert calls["removed"] == [("httpd-private", "gh-stranger")]


def test_adjust_teams_skips_committer_teams_for_projects_without_public_repos(monkeypatch):
    server, calls = make_server(monkeypatch, [("httpd-committers", "httpd committers", ["gh-stranger"], [])])
    asyncio.run(plugins.background.adjust_teams(server))
    assert calls["added"] == [] and calls["removed"] == []


def test_adjust_teams_skips_private_teams_when_ldap_gave_no_pmc(monkeypatch):
    """An empty PMC list means an LDAP failure, not a PMC that everyone left"""
    server, calls = make_server(monkeypatch, [("httpd-private", "httpd private", ["gh-humbedooh"], [])])
    server.data.projects["httpd"].private_repos.append(FakeRepo("httpd-private", True))
    server.data.projects["httpd"].pmc = []
    asyncio.run(plugins.background.adjust_teams(server))
    assert calls["added"] == [] and calls["removed"] == []


def test_adjust_teams_survives_teams_without_a_matching_project(monkeypatch):
    server, calls = make_server(monkeypatch, [("ghost-committers", "ghost committers", ["gh-stranger"], [])])
    asyncio.run(plugins.background.adjust_teams(server))
    assert calls["added"] == [] and calls["removed"] == []


def test_adjust_repositories_syncs_the_committer_team_repo_list(monkeypatch):
    server, calls = make_server(
        monkeypatch, [("httpd-committers", "httpd committers", [], ["httpd-retired"])]
    )
    project = server.data.projects["httpd"]
    project.public_repos = [FakeRepo("httpd"), FakeRepo("httpd-site")]
    server.data.github_repos = ["httpd", "httpd-site"]
    asyncio.run(plugins.background.adjust_repositories(server))
    assert sorted(calls["repo_added"]) == [("httpd-committers", "httpd"), ("httpd-committers", "httpd-site")]
    assert calls["repo_removed"] == [("httpd-committers", "httpd-retired")]


def test_adjust_repositories_only_assigns_repos_that_exist_on_github(monkeypatch):
    """A repo created on gitbox but not yet mirrored to GitHub cannot be assigned to a team"""
    server, calls = make_server(monkeypatch, [("httpd-committers", "httpd committers", [], [])])
    server.data.projects["httpd"].public_repos = [FakeRepo("httpd"), FakeRepo("httpd-brandnew")]
    server.data.github_repos = ["httpd"]
    asyncio.run(plugins.background.adjust_repositories(server))
    assert calls["repo_added"] == [("httpd-committers", "httpd")]


def test_adjust_repositories_syncs_private_teams_with_private_repos(monkeypatch):
    server, calls = make_server(monkeypatch, [("httpd-private", "httpd private", [], [])])
    project = server.data.projects["httpd"]
    project.public_repos = [FakeRepo("httpd")]
    project.private_repos = [FakeRepo("httpd-secrets", True)]
    server.data.github_repos = ["httpd", "httpd-secrets"]
    asyncio.run(plugins.background.adjust_repositories(server))
    assert calls["repo_added"] == [("httpd-private", "httpd-secrets")]
