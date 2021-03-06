import asyncio
import datetime
import sys
import time

import plugins.basetypes
import plugins.configuration
import plugins.database
import plugins.repositories
import plugins.projects
import plugins.github


class ProgTimer:
    """A simple task timer that displays when a sub-task is begun, ends, and the time taken."""
    start: float
    title: str

    def __init__(self, title):
        self.title = title

    async def __aenter__(self):
        sys.stdout.write(
            "[%s] %s...\n" % (datetime.datetime.now().strftime("%H:%M:%S"), self.title)
        )
        sys.stdout.flush()
        self.start = time.time()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print(
            "[%s] Done in %.2f seconds"
            % (datetime.datetime.now().strftime("%H:%M:%S"), time.time() - self.start)
        )


async def run_tasks(server: plugins.basetypes.Server):
    """
        Runs long-lived background data gathering tasks such as gathering repositories, projects and ldap/mfa data.

        Generally runs every 2½ minutes, or whatever is set in tasks/refresh_rate in boxer.yaml
    """

    while True:
        now = time.time()
        asf_github_org = plugins.github.GitHubOrganisation(login='apache', personal_access_token=server.config.github.token)
        await asf_github_org.get_id()  # For security reasons, we must call this before we can add/remove members
        limit, used = await asf_github_org.rate_limit_rest()
        print("Used %u out of %u REST tokens this hour." % (used, limit))
        limit, used = await asf_github_org.rate_limit_graphql()
        print("Used %u out of %u GraphQL tokens this hour." % (used, limit))

        async with ProgTimer("Gathering list of repositories on gitbox"):
            try:
                server.data.repositories = await plugins.repositories.list_all(server.config.repos)
            except Exception as e:
                print(
                    "Could not fetch repositories - gitbox down or not connected: %s"
                    % e
                )
                await asyncio.sleep(10)
                continue

        async with ProgTimer("Gathering list of repositories on GitHub"):
            github_repos = await asf_github_org.load_repositories()
        async with ProgTimer("Compiling list of projects, repos and memberships"):
            try:
                asf_org = await plugins.projects.compile_data(server.config.ldap, server.data.repositories, server.database.client)
                server.data.projects = asf_org.projects
                server.data.people = asf_org.committers
            except Exception as e:
                print(
                    "Could not fetch repositories - gitbox down or not connected: %s"
                    % e
                )

        async with ProgTimer("Gathering MFA status of GitHub users"):
            server.data.mfa = await asf_github_org.get_mfa_status()

        async with ProgTimer("Adjusting MFA status for users"):
            for person in server.data.people:
                if person.github_id and person.github_id in server.data.mfa:
                    if person.github_mfa is not server.data.mfa[person.github_id]:
                        person.github_mfa = server.data.mfa[person.github_id]
                        person.save()  # Update sqlite db if changed

        async with ProgTimer("Getting GitHub teams and their members"):
            github_teams = await asf_github_org.load_teams()
            server.data.teams = github_teams

        async with ProgTimer("Looking for missing/invalid GitHub teams"):
            await asf_github_org.setup_teams(server.data.projects)

        async with ProgTimer("Adjusting GitHub teams according to LDAP/MFA"):
            for team in github_teams:
                if team.type == 'committers':  # All we care about right now is the commit groups
                    asf_project = server.data.projects.get(team.project)
                    if asf_project:
                        ldap_github_team = asf_project.public_github_team()
                        if asf_project.committers:  # Only set if we got LDAP data back
                            added, removed = await team.set_membership(ldap_github_team)
                            if added:
                                print(f"Added {len(added)} members to team {team.slug}: {', '.join(added)}")
                            if removed:
                                print(f"Removed {len(removed)} members from team {team.slug}: {', '.join(removed)}")
                        else:
                            print(f"Could not find LDAP data for ASF project {team.project}, ignoring for now!")
                            continue
                    else:
                        print(f"Could not find an ASF project for team {team.slug}!!")

        alimit, aused = await asf_github_org.rate_limit_graphql()
        used_gql = aused
        if used < aused:
            used_gql -= used
        time_taken = time.time() - now
        print("Background task run finished after %u seconds. Used %u GraphQL tokens for this." % (time_taken, used_gql))
        await asyncio.sleep(server.config.tasks.refresh_rate)
