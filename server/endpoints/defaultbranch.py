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

import os
import time
import plugins.basetypes
import plugins.session
import plugins.github
import re
import asfpy.messaging

ADMIN_ADDITIONAL_PROJECTS = ["infrastructure", "members", "board", "foundation"]

""" GitHub/GitBox default branch mgmt endpoint for Boxer """


async def process(
        server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    if not session.credentials:
        return {"okay": False, "message": "You need to be logged in to access this endpoint."}
    
    new_default_branch = indata.get("default_branch")
    if not new_default_branch:
        return {"okay": False, "message": "Invalid branch name specified."}

    # Ensure repo exists
    repo = indata.get("repository")
    repo_filepath = None
    for _repo in server.data.repositories:
        if _repo.filename == repo:
            repo_filepath = _repo.filepath
            break
    if not repo_filepath:
        return {"okay": False, "message": "Invalid repository specified."}

    # Ensure right permissions
    m = re.match(r"^(?:incubator-)?([a-z0-9]+)(-[-0-9a-z]+)?(\.git)?$", repo)  # httpd.git or sling-foo.git etc
    if not m:
        return {"okay": False, "message": "Invalid repository name specified"}
    pmc = m.group(1)
    # TODO: use oauth.a.o data object instead of LDAP lookups
    if not session.credentials.admin and not (session.credentials.member and pmc in EXEC_ADDITIONAL_PROJECTS):
        async with plugins.ldap.LDAPClient(server.config.ldap) as lc:
            committer_list, pmc_list = await lc.get_members(pmc)
            if not pmc_list:
                return {"okay": False, "message": "Invalid project prefix '%s' specified" % pmc}
            if session.credentials.uid not in pmc_list:
                return {"okay": False, "message": "Only (I)PMC members of this project may change the default branch of a repository"}


    # Change default on GitHub:
    asf_github_org = plugins.github.GitHubOrganisation(
        login=server.config.github.org, personal_access_token=server.config.github.token
    )
    try:
        await asf_github_org.get_id()  # Must be called in order to elevate access.
        await asf_github_org.api_patch(f"https://api.github.com/repos/{server.config.github.org}/{repo}", {"default_branch": new_default_branch})
    except AssertionError as e:
        return {"okay": False, "message": "Could not archive repository on GitHub."}
    
    # Change default on gitbox (override the repo.git/HEAD file):
    with open(os.path.join(repo_filepath, "HEAD"), "w") as f:
        f.write(f"ref: refs/heads/{new_default_branch}")
        f.close()

    # Send notification to project
    asfpy.messaging.mail(
                    sender="GitBox <gitbox@apache.org>",
                    recipients=[f"private@{pmc}.apache.org"],
                    subject=f"Repository default branch changed for: {repo}",
                    message=f"User {session.credentials.email} changed the default branch of {repo} to: {new_default_branch}\n"
                )


    return {"okay": True, "message": f"Repository default branch successfully updated to {new_default_branch}."}

def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
