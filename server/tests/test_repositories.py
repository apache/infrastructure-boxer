"""Tests for repository discovery and project-name derivation"""
import asyncio

import pytest

import plugins.repositories


def make_repo(tmp_path, name, private=False, nocommit=False, description=None):
    path = tmp_path / name
    path.mkdir()
    if nocommit:
        (path / "nocommit").write_text("archived")
    if description is not None:
        (path / "description").write_text(description)
    return plugins.repositories.Repository(private, str(path))


@pytest.mark.parametrize(
    "filename,project",
    [
        ("httpd.git", "httpd"),
        ("httpd-site.git", "httpd"),
        ("httpd.site.git", "httpd"),
        ("incubator.git", "incubator"),
        ("incubator-ponymail-foal.git", "ponymail"),
        ("terraform-provider-cassandra.git", "cassandra"),  # INFRA-27355
        ("empire-db.git", "empire-db"),
        ("empire-db-site.git", "empire-db"),
    ],
)
def test_project_name_is_derived_from_the_repo_filename(tmp_path, filename, project):
    assert make_repo(tmp_path, filename).project == project


def test_filename_strips_the_git_suffix(tmp_path):
    assert make_repo(tmp_path, "httpd-site.git").filename == "httpd-site"


def test_a_nocommit_file_marks_the_repo_as_archived(tmp_path):
    assert make_repo(tmp_path, "httpd.git", nocommit=True).archived is True
    assert make_repo(tmp_path, "tomcat.git").archived is False


def test_description_is_read_from_the_description_file(tmp_path):
    repo = make_repo(tmp_path, "httpd.git", description="Apache HTTP Server")
    assert repo.description == "Apache HTTP Server"
    assert make_repo(tmp_path, "tomcat.git").description == ""


def test_list_all_finds_public_and_private_repos(tmp_path):
    public = tmp_path / "public"
    private = tmp_path / "private"
    public.mkdir()
    private.mkdir()
    (public / "httpd.git").mkdir()
    (public / "tomcat.git").mkdir()
    (public / "README.txt").write_text("not a repo")
    (private / "fundraising").mkdir()
    (private / "fundraising" / "fundraising-clients.git").mkdir()
    (private / "fundraising" / "notes.txt").write_text("not a repo either")
    cfg = plugins.repositories.RepoConfig(
        {"public": str(public), "private": str(private), "fallback": ""}
    )
    repos = asyncio.run(plugins.repositories.list_all(cfg))
    by_name = {repo.filename: repo for repo in repos}
    assert set(by_name) == {"httpd", "tomcat", "fundraising-clients"}
    assert by_name["httpd"].private is False
    assert by_name["fundraising-clients"].private is True
    assert by_name["fundraising-clients"].project == "fundraising"


def test_repoconfig_rejects_missing_directories(tmp_path):
    with pytest.raises(AssertionError):
        plugins.repositories.RepoConfig({"public": str(tmp_path / "nope"), "private": str(tmp_path)})
