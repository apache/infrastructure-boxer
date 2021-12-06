#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import plugins.basetypes
import plugins.session
import plugins.ldap
import re
import os
import aiohttp.client
import asyncio
import shutil
import asfpy.messaging

GIT_EXEC = shutil.which("git")
GB_CLONE_EXEC = "/x1/gitbox/bin/gitbox-clone"
NEW_REPO_NOTIFY = 'private@infra.apache.org'
NEW_REPO_NOTIFY_MSG = """
A new repository has been set up by %(uid)s@apache.org: %(reponame)s

Commit mail target: %(commit_mail)s
Dev/issue mail target: %(issue_mail)s

The repository can be found at:
GitBox: %(repourl_gb)s
GitHub: %(repourl_gh)s

With regards,
Boxer Git Management Services
"""

""" Repository editor endpoint for Boxer"""


async def process(
        server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    if not session.credentials:
        return {"okay": False, "message": "You need to be logged in to access this end point"}

    action = indata.get("action")
    if action == "create":
        reponame = indata.get("repository")
        uid = session.credentials.uid
        private = indata.get("private", False)
        m = re.match(r"^([a-z0-9]+)(-[-0-9a-z]+)?\.git$", reponame)  # httpd.git or sling-foo.git etc
        if not m:
            return {"okay": False, "message": "Invalid repository name specified"}
        pmc = m.group(1)
        title = indata.get("title", "Apache %s" % pmc)

        # Check LDAP ownership
        if not session.credentials.admin:
            async with plugins.ldap.LDAPClient(server.config.ldap) as lc:
                committer_list, pmc_list = await lc.get_members(pmc)
                if not pmc_list:
                    return {"okay": False, "message": "Invalid project prefix '%s' specified" % pmc}
                if session.credentials.uid not in pmc_list:
                    return {"okay": False, "message": "Only (I)PMC members of this project may create repositories"}

        repourl_gh = f"https://github.com/{server.config.github.org}/{reponame}"
        repourl_gb = f"https://gitbox-test.apache.org/repos/asf/{reponame}"
        if not private:
            repo_path = os.path.join(server.config.repos.public, reponame)
            if os.path.exists(repo_path):
                return {"okay": False, "message": "A repository by that name already exists"}
        else:
            repourl_gb = f"https://gitbox-test.apache.org/repos/private/{pmc}/{reponame}"
            repo_path = os.path.join(server.config.repos.private, pmc, reponame)
            pmc_dir = os.path.join(server.config.repos.private, pmc)
            if not os.path.isdir(pmc_dir):
                os.mkdir(pmc_dir)
            if os.path.exists(repo_path):
                return {"okay": False, "message": "A repository by that name already exists"}

        # Get last bits of info
        commit_mail = indata.get("commit", "commits@%s.apache.org" % pmc)
        issue_mail = indata.get("issue", "dev@%s.apache.org" % pmc)

        # Create the repo
        rv = await create_repo(server, reponame, title, pmc, private)
        if rv is True:
            params = ['-c', commit_mail, '-d', title, "git@github.com:%s/%s" % (server.config.github.org, reponame),
                      repo_path]
            proc = await asyncio.create_subprocess_exec(
                GB_CLONE_EXEC, *params, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            # Everything went okay?
            if proc.returncode == 0:
                asfpy.messaging.mail(
                    recipient = NEW_REPO_NOTIFY,
                    subject = f"New GitBox/GitHub repository set up: {reponame}" ,
                    message = NEW_REPO_NOTIFY_MSG % locals()
                )
                return {"okay": True, "message": "Repository created!"}
            else:
                return {"okay": False, "message": str(stderr)}
        else:
            return {"okay": False, "message": rv}


async def create_repo(server, repo, title, pmc, private = False):
    url = "https://api.github.com/orgs/%s/repos" % server.config.github.org
    session_timeout = aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=15)
    async with aiohttp.client.ClientSession(timeout=session_timeout) as hc:
        rv = await hc.post(url, json={
                'name': repo,
                'description': title,
                'homepage': "https://%s.apache.org/" % pmc,
                'private': private,
                'has_issues': False,
                'has_projects': False,
                'has_wiki': False
            },
            headers={'Authorization': "token %s" % server.config.github.token}
        )
        if rv.status == 201:
            return True
        else:
            txt = await rv.text()
            return txt


def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
