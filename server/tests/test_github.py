"""Tests for the GitHub organisation/team model and its membership diffing"""
import asyncio
import json

import pytest

import plugins.github
import plugins.projects


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


def make_org():
    org = plugins.github.GitHubOrganisation(login="apache", personal_access_token="x" * 40)
    org.orgid = 1
    return org


def test_organisation_requires_some_kind_of_token():
    with pytest.raises(AssertionError):
        plugins.github.GitHubOrganisation(login="apache")


def test_organisation_builds_the_right_auth_header():
    pat = plugins.github.GitHubOrganisation(personal_access_token="x" * 40)
    assert pat.api_headers["Authorization"] == "token " + "x" * 40
    bearer = plugins.github.GitHubOrganisation(bearer_token="y" * 40)
    assert bearer.api_headers["Authorization"] == "bearer " + "y" * 40


def test_team_derives_project_and_type_from_its_name():
    team = plugins.github.GitHubTeam(make_org(), team_node("httpd-committers", "httpd committers"))
    assert team.project == "httpd"
    assert team.type == "committers"


def test_team_name_splits_on_the_first_space_only():
    """empire-db committers must resolve to the empire-db project, not empire"""
    team = plugins.github.GitHubTeam(make_org(), team_node("empire-db-committers", "empire-db committers"))
    assert team.project == "empire-db"
    assert team.type == "committers"


def test_team_without_a_role_suffix_is_treated_as_admin():
    team = plugins.github.GitHubTeam(make_org(), team_node("admins", "admins"))
    assert team.project == "root"
    assert team.type == "admin"


def test_team_reads_members_and_repositories_from_the_node():
    team = plugins.github.GitHubTeam(
        make_org(), team_node("httpd-committers", "httpd committers", ["gh-humbedooh"], ["httpd-site"])
    )
    assert team.members == ["gh-humbedooh"]
    assert team.repos == ["httpd-site"]


def test_get_team_locates_committer_and_private_teams():
    org = make_org()
    committers = plugins.github.GitHubTeam(org, team_node("httpd-committers", "httpd committers"))
    private = plugins.github.GitHubTeam(org, team_node("httpd-private", "httpd private"))
    org.teams = [committers, private]
    assert org.get_team("httpd", private=False) is committers
    assert org.get_team("httpd", private=True) is private
    assert org.get_team("tomcat", private=False) is None


def make_team(monkeypatch, members=(), repos=()):
    team = plugins.github.GitHubTeam(make_org(), team_node("httpd-committers", "httpd committers", members, repos))
    calls = {"added": [], "removed": [], "repo_added": [], "repo_removed": []}

    async def add_member(github_id):
        calls["added"].append(github_id)

    async def remove_member(github_id):
        calls["removed"].append(github_id)

    async def add_repository(reponame):
        calls["repo_added"].append(reponame)

    async def remove_repository(reponame):
        calls["repo_removed"].append(reponame)

    monkeypatch.setattr(team, "add_member", add_member)
    monkeypatch.setattr(team, "remove_member", remove_member)
    monkeypatch.setattr(team, "add_repository", add_repository)
    monkeypatch.setattr(team, "remove_repository", remove_repository)
    return team, calls


def test_set_membership_adds_missing_and_removes_extra_members(monkeypatch):
    team, calls = make_team(monkeypatch, members=["gh-humbedooh", "gh-stranger"])
    added, removed = asyncio.run(team.set_membership(["gh-humbedooh", "gh-sk"]))
    assert sorted(added) == sorted(calls["added"]) == ["gh-sk"]
    assert sorted(removed) == sorted(calls["removed"]) == ["gh-stranger"]


def test_set_membership_leaves_ci_accounts_alone(monkeypatch):
    """asf-ci* robots are managed by hand, so the sync must neither add nor remove them"""
    team, calls = make_team(monkeypatch, members=["asf-ci-deploy", "gh-humbedooh"])
    added, removed = asyncio.run(team.set_membership(["gh-humbedooh", "asf-ci-other"]))
    assert added == [] and removed == []
    assert calls["added"] == [] and calls["removed"] == []


def test_set_repositories_adds_missing_and_removes_extra_repos(monkeypatch):
    team, calls = make_team(monkeypatch, repos=["httpd-site", "httpd-retired"])
    added, removed = asyncio.run(team.set_repositories(["httpd-site", "httpd"]))
    assert sorted(added) == sorted(calls["repo_added"]) == ["httpd"]
    assert sorted(removed) == sorted(calls["repo_removed"]) == ["httpd-retired"]


def stub_post(monkeypatch, org):
    posted = []

    async def fake_post(url, jsdata=None):
        posted.append((url, jsdata))
        return json.dumps({"id": 4321})

    monkeypatch.setattr(org, "api_post", fake_post)
    return posted


def test_add_team_posts_the_name_and_privacy(monkeypatch):
    org = make_org()
    posted = stub_post(monkeypatch, org)
    teamid = asyncio.run(org.add_team("httpd"))
    assert teamid == 4321
    url, jsdata = posted[0]
    assert url == "https://api.github.com/orgs/apache/teams"
    assert jsdata == {"name": "httpd committers", "privacy": "secret"}


def test_add_team_requires_the_org_id_first():
    """Membership calls are made by database ID, so creating teams before get_id() must fail loudly"""
    org = plugins.github.GitHubOrganisation(login="apache", personal_access_token="x" * 40)
    with pytest.raises(AssertionError):
        asyncio.run(org.add_team("httpd"))


def build_project(name, committers, public_repo=None, private_repo=None):
    org = plugins.projects.Organization()
    project = org.add_project(name, list(committers), list(committers))
    for committer in project.committers:
        committer.github_login = f"gh-{committer.asf_id}"
        committer.github_mfa = True
    if public_repo:
        project.public_repos.append(public_repo)
    if private_repo:
        project.private_repos.append(private_repo)
    return project


class FakeRepo:
    def __init__(self, filename, private=False):
        self.filename = filename
        self.private = private


def test_setup_teams_creates_a_private_team_for_private_repos(monkeypatch):
    org = make_org()
    posted = stub_post(monkeypatch, org)
    project = build_project("httpd", ["humbedooh"], private_repo=FakeRepo("httpd-private", True))
    asyncio.run(org.setup_teams({"httpd": project}, {}, {}))
    assert [jsdata["name"] for url, jsdata in posted] == ["httpd private"]
    assert [jsdata["privacy"] for url, jsdata in posted] == ["secret"]
    assert [t.slug for t in org.teams] == ["httpd-private"]
    assert org.teams[0].type == "private"


def test_setup_teams_does_not_recreate_an_existing_private_team(monkeypatch):
    org = make_org()
    posted = stub_post(monkeypatch, org)
    org.teams = [plugins.github.GitHubTeam(org, team_node("httpd-private", "httpd private"))]
    project = build_project("httpd", ["humbedooh"], private_repo=FakeRepo("httpd-private", True))
    asyncio.run(org.setup_teams({"httpd": project}, {}, {}))
    assert posted == []
