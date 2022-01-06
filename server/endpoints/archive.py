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

ADMIN_ADDITIONAL_PROJECTS = ["infrastructure", "members", "board", "foundation"]

""" GitHub/GitBox archival endpoint for Boxer """


async def process(
        server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    if not session.credentials or not session.credentials.admin:
        return {"okay": False, "message": "You need administrative access to archive repositories."}

    # Ensure repo exists
    repo = indata.get("repository")
    if not repo or not any(x.filename == repo for x in server.data.repositories):
        return {"okay": False, "message": "Invalid repository specified."}

    # Archive on GitHub:
    asf_github_org = plugins.github.GitHubOrganisation(
        login=server.config.github.org, personal_access_token=server.config.github.token
    )
    try:
        await asf_github_org.get_id()  # Must be called in order to elevate access.
        await asf_github_org.api_patch(f"https://api.github.com/repos/{server.config.github.org}/{repo}", {"archived": True})
    except AssertionError as e:
        return {"okay": False, "message": "Could not archive repository on GitHub."}

    # Archive on GitBox:
    repo_path = None
    for repository in server.data.repositories:
        if repository.filename == repo:
            repo_path = repository.filepath
    if not repo_path:
        return {"okay": False, "message": "Could not locate repository on GitBox - please contact ASF Infra."}
    with open(os.path.join(repo_path, "nocommit"), "w") as f:
        now = time.ctime()
        f.write(f"Archived at {now} by {session.credentials.uid} ({session.credentials.name})\n")
        f.close()

    return {"okay": True, "message": "Repository successfully archived."}

def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
