from __future__ import annotations
import plugins.basetypes
import plugins.ldap
import plugins.github
import plugins.repositories
import os
import typing


class ServerConfig:

    def __init__(self, subyaml: dict):
        self.ip: str = subyaml.get("bind", "0.0.0.0")
        self.port: int = int(subyaml.get("port", 8080))
        self.traceback: bool = bool(subyaml.get('traceback', False))


class TaskConfig:
    def __init__(self, subyaml: dict):
        self.refresh_rate: int = int(subyaml.get("refresh_rate", 150))
        assert self.refresh_rate >= 60, "Refresh rate must be at least 60 seconds!"


class OAuthConfig:
    def __init__(self, subyaml: dict):
        self.authoritative_domains: typing.List[str] = subyaml.get("authoritative_domains", [])
        self.admins: typing.List[str] = subyaml.get("admins", "").split(' ')
        self.github_client_id: str = subyaml.get("github_client_id", "")
        self.github_client_secret: str = subyaml.get("github_client_secret", "")
        assert isinstance(self.github_client_id, str), "GitHub client ID must be a string"
        assert isinstance(self.github_client_secret, str), "GitHub client secret must be a string"


class DBConfig:
    def __init__(self, subyaml: dict):
        self.dbtype: str = subyaml.get("dbtype", "sqlite")
        self.dbfile: str = subyaml.get("dbfile", "boxer.db")
        assert self.dbtype == 'sqlite', "DB type must be SQLite for now, I dunno other types"
        assert isinstance(self.dbfile, str) and os.path.exists(self.dbfile), "DB File must exist on disk!"


class GitHubConfig:

    def __init__(self, subyaml: dict):
        self.token: str = subyaml.get("token", "")
        self.org: str = subyaml.get("org", "asftest")
        assert isinstance(self.token, str) and len(self.token) == 40, "GitHub token must be a valid token!"


class Configuration:

    def __init__(self, yml: dict):
        self.server: ServerConfig = ServerConfig(yml.get("server", {}))
        self.database: DBConfig = DBConfig(yml.get("database", {}))
        self.tasks: TaskConfig = TaskConfig(yml.get("tasks", {}))
        self.oauth: OAuthConfig = OAuthConfig(yml.get("oauth", {}))
        self.repos: plugins.repositories.RepoConfig = plugins.repositories.RepoConfig(yml.get("repositories", {}))
        self.ldap: plugins.ldap.LDAPConfig = plugins.ldap.LDAPConfig(yml.get("ldap", {}))
        self.github: GitHubConfig = GitHubConfig(yml.get("github", {}))


class InterData:
    """
        A mix of various global variables used throughout processes
    """

    def __init__(self):
        self.repositories: list = []
        self.github_repos: list = []
        self.sessions: dict = {}
        self.people: list = []
        self.projects: dict = {}
        self.mfa: dict = {}
        self.teams: typing.List[plugins.github.GitHubTeam] = []
        self.pmcs = {}
        self.podlings = []

