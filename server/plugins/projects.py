import plugins.ldap
import plugins.repositories
import asfpy.sqlite
import typing
import datetime


class Committer:
    def save(self, dbhandle: asfpy.sqlite.DB):
        document = {
            "asfid": self.asf_id,
            "githubid": self.github_login,
            "mfa": 1 if self.github_mfa else 0,
            "updated": datetime.datetime.now(),
        }
        dbhandle.upsert("ids", document, asfid=self.asf_id)

    def __init__(
        self, asf_id: str, linkdb: asfpy.sqlite.DB,
    ):
        self.asf_id = asf_id
        self.repositories: typing.Set[plugins.repositories.Repository] = set()
        self.projects: typing.Set[Project] = set()
        if linkdb:
            row = linkdb.fetchone("ids", limit=1, asfid=asf_id)
        else:
            row = None
        if row:
            self.github_login = row["githubid"]
            self.github_mfa = bool(row["mfa"])
            self.real_name = ""
        else:
            self.github_login = None
            self.github_mfa = False
            self.real_name = ""

    def __repr__(self):
        return self.asf_id

    def __eq__(self, other):
        if isinstance(other, str):
            return other == self.asf_id
        if not isinstance(other, Committer):
            return False
        return self.asf_id == other.asf_id

    def __hash__(self):
        return hash((self.asf_id,))


class Project:
    def __init__(self, org: "Organization", name: str, committers: list, pmc: list):
        self.name: str = name
        self.committers: typing.List[Committer] = []
        for committer in committers:
            account = org.add_committer(committer)
            self.committers.append(account)
            account.projects.add(self)
        self.pmc: typing.List[Committer] = []
        for owner in pmc or []:
            account = org.add_committer(owner)
            self.pmc.append(account)
            account.projects.add(self)
        self.public_repos: typing.List[plugins.repositories.Repository] = []
        self.private_repos: typing.List[plugins.repositories.Repository] = []

    def __repr__(self):
        return f"Project<{self.name}>"

    def add_repository(self, repo: plugins.repositories.Repository, private: bool):
        """Adds a repository to a project and assigns the repo to the commmitter/PMC group as applicable"""
        if private:
            self.private_repos.append(repo)
            for account in self.pmc:
                account.repositories.add(repo)
        else:
            self.public_repos.append(repo)
            for account in self.committers:
                account.repositories.add(repo)

    def public_github_team(self, mfa = None):
        """Returns the GitHub IDs of everyone that should be on the GitHub team for this project"""
        team_ids = set()
        for committer in self.committers:
            if mfa:
                if mfa.get(committer.github_login):
                    team_ids.add(committer.github_login)
            elif committer.github_mfa:
                team_ids.add(committer.github_login)
        return list(team_ids)

    def private_github_team(self, mfa = None):
        """Returns the GitHub IDs of everyone that should be on the GitHub private team for this project"""
        team_ids = set()
        for committer in self.pmc:
            if mfa:
                if mfa.get(committer.github_login):
                    team_ids.add(committer.github_login)
            elif committer.github_mfa:
                team_ids.add(committer.github_login)
        return list(team_ids)


class Organization:

    def __init__(self, linkdb: asfpy.sqlite.DB = None):
        self.committers: typing.List[Committer] = list()
        self.projects: typing.Dict[str, Project] = dict()
        self.linkdb: typing.Optional[asfpy.sqlite.DB] = linkdb

    def add_project(self, name: str, committers: typing.List[str], pmc: typing.List[str]) -> typing.Optional[Project]:
        if name and name not in self.projects:
            project = Project(org=self, name=name, committers=committers, pmc=pmc)
            if project:
                self.projects[name] = project
            return project
        return None

    def add_committer(self, asf_id: str):
        """Adds a new committer to the organization.
        If already found in previous projects, returns the old committer object"""
        if asf_id not in self.committers:
            committer = Committer(asf_id, self.linkdb)
            self.committers.append(committer)
            return committer
        else:
            for committer in self.committers:
                if committer.asf_id == asf_id:
                    return committer


async def compile_data(
    ldap: plugins.ldap.LDAPConfig,
    repositories: typing.List[plugins.repositories.Repository],
    linkdb: typing.Optional[asfpy.sqlite.DB]
) -> Organization:
    """Compiles a comprehensive list of projects and people associated with them"""
    org = Organization(linkdb=linkdb)
    discovered = 0
    async with plugins.ldap.LDAPClient(ldap) as lc:
        for repo in repositories:
            project = repo.project
            if not project:
                continue
            if project not in org.projects:
                committers, pmc = await lc.get_members(project)
                if committers and pmc:
                    discovered += 1
                    # print(f"Discovered project: {project} - {len(committers)} committers, {len(pmc)} in pmc")
                    if discovered % 50 == 0:
                        print("Discovered %u projects so far..." % discovered)
                org.add_project(name=project, committers=committers, pmc=pmc)
            xproject = org.projects[project]
            xproject.add_repository(repo, repo.private)

    return org
