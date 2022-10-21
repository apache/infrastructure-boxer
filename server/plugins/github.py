"""Miscellaneous GitHub classes for Boxer"""
import aiohttp
import typing
import json
import plugins.projects
import dateutil.parser
import asyncio

GRAPHQL_URL = "https://api.github.com/graphql"
DEBUG = False  # Set to True to disable GitHub API calls


class GitHubOrganisation:
    """Simple GitHub Organization with GraphQL mixins for added speed"""

    login: str
    orgid: typing.Optional[int]
    api_headers: typing.Dict[str, str]
    teams: typing.List["GitHubTeam"]
    repositories: typing.List[str]

    def __init__(
        self,
        login: str = "apache",
        personal_access_token: str = "",
        bearer_token: str = "",
    ):
        """
        Instantiate a GitHub Organization

        :param login: The GitHub organization to instantiate, e.g. apache
        :param personal_access_token: Personal access token from an org owner account
        :param bearer_token: If using bearer token instead of PAT, use it here
        """
        assert (
            personal_access_token or bearer_token
        ), "You must specify either a PAT or a bearer token!"
        self.login = login
        self.orgid = None
        self.teams = list()
        self.repositories = list()
        if personal_access_token:
            self.api_headers = {"Authorization": "token %s" % personal_access_token}
        else:
            self.api_headers = {"Authorization": "bearer %s" % bearer_token}

    async def get_id(self):
        """Fetches the organization's GitHub ID.
           This must be called once before membership or repository additions/deletions, to ensure
           we can perform these calls using database IDs only."""
        if self.orgid is None:
            async with aiohttp.ClientSession(headers=self.api_headers) as session:
                url = f"https://api.github.com/orgs/{self.login}"
                async with session.get(url) as rv:
                    js = await rv.json()
                    self.orgid = js["id"]
        return self.orgid

    async def api_delete(self, url: str):
        if DEBUG:
            print("[DEBUG] DELETE", url)
        else:
            async with aiohttp.ClientSession(headers=self.api_headers) as session:
                async with session.delete(url) as rv:
                    txt = await rv.text()
                    assert rv.status == 204, f"Unexpected return code for DELETE on {url}: {rv.status}"
                    await asyncio.sleep(1.05)
                    return txt

    async def api_put(self, url: str, jsdata: typing.Optional[dict] = None):
        if DEBUG:
            print("[DEBUG] PUT", url)
        else:
            async with aiohttp.ClientSession(headers=self.api_headers) as session:
                async with session.put(url, json=jsdata) as rv:
                    txt = await rv.text()
                    assert rv.status in [200, 204], f"Unexpected return code for PUT on {url}: {rv.status}"
                    await asyncio.sleep(1.05)
                    return txt

    async def api_patch(self, url: str, jsdata: typing.Optional[dict] = None):
        if DEBUG:
            print("[DEBUG] PATCH", url)
        else:
            async with aiohttp.ClientSession(headers=self.api_headers) as session:
                async with session.patch(url, json=jsdata) as rv:
                    txt = await rv.text()
                    assert rv.status in [200, 204], f"Unexpected return code for PATCH on {url}: {rv.status}"
                    await asyncio.sleep(1.05)
                    return txt


    async def api_post(self, url: str, jsdata: typing.Optional[dict] = None):
        if DEBUG:
            print("[DEBUG] POST", url)
        else:
            async with aiohttp.ClientSession(headers=self.api_headers) as session:
                async with session.post(url, json=jsdata) as rv:
                    txt = await rv.text()
                    assert rv.status == 201, f"Unexpected retun code for POST on {url}: {rv.status}"
                    await asyncio.sleep(1.05)
                    return txt

    def get_team(self, team: str, private: bool) -> typing.Optional["GitHubTeam"]:
        """Locate a GitHub team and return it"""
        slug = f"{team}-committers"
        if private:
            slug = f"{team}-private"
        for xteam in self.teams:
            if xteam.slug == slug:
                return xteam
        return None

    async def rate_limit_rest(self):
        """Fetches the hourly REST API limit and how many uses have been expended this hour."""
        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            url = "https://api.github.com/rate_limit"
            async with session.get(url) as rv:
                js = await rv.json()
                return js["rate"]["limit"], js["rate"]["used"], js["rate"]["reset"]

    async def rate_limit_graphql(self):
        """Fetches the hourly GraphQL API limit and how many uses have been expended this hour."""
        query = """
        {
            rateLimit
            {
                limit
                cost
                used
                resetAt
            }
        }
        """
        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            async with session.post(GRAPHQL_URL, json={"query": query}) as rv:
                js = await rv.json()
                resets = dateutil.parser.parse(js["data"]["rateLimit"]["resetAt"]).timestamp()
                return js["data"]["rateLimit"]["limit"], js["data"]["rateLimit"]["used"], resets

    async def load_teams(self) -> typing.List["GitHubTeam"]:
        """Loads all GitHub teams in this organization using GraphQL"""
        query = """
        {
            organization(login: "%s") {
                teams(first: 100, after:%s) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    edges {
                        node {
                            name
                            slug
                            databaseId
                            members {
                                totalCount
                                edges {
                                    node {
                                        login
                                    }
                                }
                            }
                            repositories {
                                totalCount
                                edges {
                                    node {
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        teams = []

        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            next_page = True
            after = "null"
            while next_page:
                async with session.post(
                    GRAPHQL_URL, json={"query": query % (self.login, after)}
                ) as rv:
                    js = await rv.json()
                    for edge in js["data"]["organization"]["teams"]["edges"]:
                        team = GitHubTeam(self, edge)
                        total_members = edge["node"]["members"]["totalCount"]
                        total_repos = edge["node"]["repositories"]["totalCount"]
                        slug = edge["node"]["slug"]
                        if total_members > 100:
                            print(
                                f"{slug} has {total_members} members, need to fill specifically..."
                            )
                            await team.get_members()
                            print("Filled with %u members!" % len(team.members))
                        if total_repos > 100:
                            print(
                                f"{slug} has {total_repos} repos assigned, need to fill specifically..."
                            )
                            await team.get_repositories()
                            print("Filled with %u repos!" % len(team.repos))
                        teams.append(team)
                    endcursor = js["data"]["organization"]["teams"]["pageInfo"]["endCursor"]
                    next_page = endcursor not in [None, "null"]  # GraphQL is broken, look for null value here, do not trust hasNextPage
                    if next_page:
                        after = '"%s"' % endcursor
        self.teams = teams
        return teams

    async def load_repositories(self) -> typing.List[str]:
        """Loads all GitHub repositories in this organization using GraphQL"""
        query = """
        {
            organization(login: "%s") {
                repositories(first: 100, after:%s, orderBy: {field: CREATED_AT, direction: ASC}) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    edges {
                        node {
                            name
                            databaseId
                        }
                    }
                }
            }
        }
        """
        repos = []
        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            next_page = True
            after = "null"
            while next_page:
                async with session.post(
                    GRAPHQL_URL, json={"query": query % (self.login, after)}
                ) as rv:
                    js = await rv.json()
                    for edge in js["data"]["organization"]["repositories"]["edges"]:
                        repo = edge['node']['name']
                        repos.append(repo)
                    endcursor = js["data"]["organization"]["repositories"]["pageInfo"]["endCursor"]
                    next_page = endcursor not in [None, "null"]  # GraphQL is broken, look for null value here, do not trust hasNextPage
                    if next_page:
                        after = '"%s"' % endcursor
        self.repositories = repos
        return repos

    async def get_mfa_status(self) -> dict:
        """Get MFA status for all org members, return as a dict[str, bool] of people and whether 2fa is enabled"""
        query = """
        {
            organization(login: "%s") {
                membersWithRole(first: 100, after:%s) {
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                    edges {
                        hasTwoFactorEnabled
                        node {
                            login
                        }
                    }
                }
            }
        }
        """

        mfa = {}

        async with aiohttp.ClientSession(headers=self.api_headers) as session:
            next_page = True
            after = "null"
            while next_page:
                async with session.post(
                    GRAPHQL_URL, json={"query": query % (self.login, after)}
                ) as rv:
                    js = await rv.json()
                    for user in js["data"]["organization"]["membersWithRole"]["edges"]:
                        login = user["node"]["login"]
                        mfa_status = user["hasTwoFactorEnabled"]
                        mfa[login] = mfa_status
                    next_page = js["data"]["organization"]["membersWithRole"][
                        "pageInfo"
                    ]["hasNextPage"]
                    after = (
                        '"%s"'
                        % js["data"]["organization"]["membersWithRole"]["pageInfo"][
                            "endCursor"
                        ]
                    )
        mfa_enabled = len([x for x in mfa.values() if x is True])
        mfa_disabled = len([x for x in mfa.values() if x is False])
        print("%u with 2FA, %u without!" % (mfa_enabled, mfa_disabled))
        return mfa

    async def add_team(self, project: str, role: str = "committers") -> typing.Optional[int]:
        """Adds a new GitHub team to the organization"""
        assert self.orgid, "Parent GitHubOrganization needs a call to .get_id() prior to membership updates!"
        assert project, "GitHub team needs a name to be added to the organization"
        url = f"https://api.github.com/orgs/{self.login}/teams"
        data = {
            "name": f"{project} {role}",
        }
        txt = await self.api_post(url, jsdata=data)
        if txt:
            js = json.loads(txt)
            assert 'id' in js and js['id'], \
                "GitHub did not respond with a Team ID for the new team, something wrong?: \n" + txt
            print(f"Team '{project} {role}' with ID {js['id']} created.")
            return js['id']
        else:
            raise AssertionError("Github did not respond with a JSON payload!!")

    async def setup_teams(self, projects: typing.Dict[str, plugins.projects.Project]):
        """Looks for and sets up missing teams on GitHub"""
        for project in projects.values():

            # Check if public team needs to be made
            committer_team = f"{project.name} committers"
            if project.public_repos and committer_team not in self.teams:
                print(f"Team '{project.name} committers' was not found on GitHub, setting it up for the first time.")
                teamid = await self.add_team(project.name, "committers")
                nodedata = {
                    "node": {
                        "databaseId": teamid,
                        "slug": committer_team.replace(" ", "-"),
                        "name": committer_team,
                        "members": {
                            "edges": []
                        },
                        "repositories": {
                            "edges": []
                        },
                    },
                }
                newteam = GitHubTeam(self, nodedata)
                self.teams.append(newteam)

            # Check if private (pmc) team needs to be made
            private_team = f"{project.name} private"
            if project.private_repos and private_team not in self.teams:
                print(
                    f"Team '{project.name} private' was not found on GitHub, setting it up for the first time.")
                teamid = await self.add_team(project.name, "private")
                nodedata = {
                    "node": {
                        "databaseId": teamid,
                        "slug": private_team.replace(" ", "-"),
                        "name": private_team,
                        "members": {
                            "edges": []
                        },
                        "repositories": {
                            "edges": []
                        },
                    },
                }
                newteam = GitHubTeam(self, nodedata)
                self.teams.append(newteam)


class GitHubTeam:
    org: GitHubOrganisation
    id: int
    slug: str
    name: str
    project: str
    type: str
    members: list
    repos: list

    def __init__(self, org: GitHubOrganisation, nodedata):
        self.org = org
        self.id = nodedata["node"]["databaseId"]
        self.slug = nodedata["node"]["slug"]
        self.name = nodedata["node"]["name"].lower()
        if " " in self.name:
            self.project, self.type = self.name.lower().split(
                " ", 1
            )  # empire-db committers -> "empire-db" + "committers"
        else:
            self.project = "root"
            self.type = "admin"
        self.members = []
        self.repos = []
        for member in nodedata["node"]["members"]["edges"]:
            self.members.append(member["node"]["login"])
        for repo in nodedata["node"]["repositories"]["edges"]:
            if repo:
                self.repos.append(repo["node"]["name"])

    def __eq__(self, other):
        if isinstance(other, str):
            return other == self.name
        if not isinstance(other, GitHubTeam):
            return False
        return self.name == other.slug

    def __hash__(self):
        return self.name.lower()

    async def get_members(self):
        """Fetches all members of a team using GraphQL"""
        query = """
            {
                organization (login: "%s") {
                    team(slug: "%s") {
                        members(first: 100, after:%s) {
                            totalCount
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                            edges {
                                node {
                                    login
                                }
                            }
                        }
                    }
                }
            }
            """

        async with aiohttp.ClientSession(headers=self.org.api_headers) as session:
            next_page = True
            after = "null"
            while next_page:
                async with session.post(
                    GRAPHQL_URL,
                    json={"query": query % (self.org.login, self.slug, after)},
                ) as rv:
                    js = await rv.json()
                    for edge in js["data"]["organization"]["team"]["members"]["edges"]:
                        login = edge["node"]["login"]
                        if login not in self.members:
                            self.members.append(login)
                    next_page = js["data"]["organization"]["team"]["members"][
                        "pageInfo"
                    ]["hasNextPage"]
                    after = (
                        '"%s"'
                        % js["data"]["organization"]["team"]["members"]["pageInfo"][
                            "endCursor"
                        ]
                    )

    async def get_repositories(self):
        """Fetches all repositories belonging to a GitHub Team using GraphQL"""
        query = """
            {
                organization (login: "%s") {
                    team(slug: "%s") {
                        repositories(first: 100, after:%s) {
                            totalCount
                            pageInfo {
                                hasNextPage
                                endCursor
                            }
                            edges {
                                node {
                                    name
                                }
                            }
                        }
                    }
                }
            }
            """

        async with aiohttp.ClientSession(headers=self.org.api_headers) as session:
            next_page = True
            after = "null"
            while next_page:
                async with session.post(
                    GRAPHQL_URL,
                    json={"query": query % (self.org.login, self.slug, after)},
                ) as rv:
                    js = await rv.json()
                    for edge in js["data"]["organization"]["team"]["repositories"][
                        "edges"
                    ]:
                        if edge:
                            reponame = edge["node"]["name"]
                            if reponame not in self.repos:
                                self.repos.append(reponame)
                    next_page = js["data"]["organization"]["team"]["repositories"][
                        "pageInfo"
                    ]["hasNextPage"]
                    after = (
                        '"%s"'
                        % js["data"]["organization"]["team"]["repositories"][
                            "pageInfo"
                        ]["endCursor"]
                    )

    async def set_membership(
        self, github_ids: typing.List[str], ignore_prefix: str = "asf-ci"
    ) -> typing.Tuple[list, list]:
        """Adjusts GitHub teams according to the list provided, removing people that are a member of the team but
           not on the provided list, and adding those missing from the team
           :param github_ids:
           :param ignore_prefix:
           :return: A tuple of github IDs added and removed"""
        github_team = set([x for x in self.members if not x.startswith(ignore_prefix)])
        asf_team = set([x for x in github_ids if not x.startswith(ignore_prefix)])
        to_remove = github_team - asf_team
        to_add = asf_team - github_team

        # If we are okay, and we have people to add/remove, do so.
        for gh_person in to_add:
            await self.add_member(gh_person)
        for gh_person in to_remove:
            await self.remove_member(gh_person)
        return list(to_add), list(to_remove)

    async def add_member(self, github_id: str):
        """Adds a new person to this github team"""
        assert (
            self.org.orgid
        ), "Parent GitHubOrganization needs a call to .get_id() prior to membership updates!"
        url = f"https://api.github.com/organizations/{self.org.orgid}/team/{self.id}/memberships/{github_id}"
        await self.org.api_put(url)

    async def remove_member(self, github_id: str):
        """Removes a new person from this github team"""
        assert (
            self.org.orgid
        ), "Parent GitHubOrganization needs a call to .get_id() prior to membership updates!"
        url = f"https://api.github.com/organizations/{self.org.orgid}/team/{self.id}/memberships/{github_id}"
        await self.org.api_delete(url)

    async def set_repositories(self, repositories: typing.List[str]) -> typing.Tuple[list, list]:
        """Assigns a list of repositories to a team. Returns a tuple of repos added and removed from the team"""
        repos_assigned = set(self.repos)
        repos_to_assign = set(repositories)
        to_add = repos_to_assign - repos_assigned
        to_remove = repos_to_assign - repos_to_assign
        for repo in to_add:
            await self.add_repository(repo)
        for repo in to_remove:
            await self.remove_repository(repo)
        return list(to_add), list(to_remove)

    async def remove_repository(self, reponame: str):
        """Removes a single repository from the team"""
        assert (
            self.org.orgid
        ), "Parent GitHubOrganization needs a call to .get_id() prior to membership updates!"
        url = f"https://api.github.com/organizations/{self.org.orgid}/team/{self.id}/repos/{self.org.login}/{reponame}"
        await self.org.api_delete(url)

    async def add_repository(self, reponame: str):
        """Adds a single repository to the team"""
        assert (
            self.org.orgid
        ), "Parent GitHubOrganization needs a call to .get_id() prior to membership updates!"
        url = f"https://api.github.com/organizations/{self.org.orgid}/team/{self.id}/repos/{self.org.login}/{reponame}"
        await self.org.api_put(url, {'permission': 'push'})
