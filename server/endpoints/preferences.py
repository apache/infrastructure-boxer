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

ADMIN_ADDITIONAL_PROJECTS = ["infrastructure", "members", "board", "foundation"]
EXEC_ADDITIONAL_PROJECTS = ["members", "board", "foundation"]

""" Generic preferences endpoint for Boxer"""


async def process(
    server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    github_data = None

    in_github_org = False
    if session.credentials and session.credentials.github_login in server.data.mfa:
        in_github_org = True
    if session.credentials:
        for p in server.data.people:
            if p.asf_id == session.credentials.uid:
                github_data = {
                    "repositories": [x.filename for x in p.repositories if x.filename in server.data.github_repos],
                    "private": [x.filename for x in p.repositories if x.private and x.filename in server.data.github_repos],
                    "mfa": p.github_mfa,
                    "login": p.github_login,
                }
                break
    pmcs = []
    all_projects = set(server.data.pmcs.keys())
    if session.credentials:
        for project, data in server.data.pmcs.items():
            if session.credentials.uid in data:
                pmcs.append(project)
        if session.credentials.admin:
            all_projects.update(ADMIN_ADDITIONAL_PROJECTS)
        elif session.credentials.member:
            all_projects.update(EXEC_ADDITIONAL_PROJECTS)
            pmcs.extend(EXEC_ADDITIONAL_PROJECTS)
            pmcs = list(sorted(pmcs))

    prefs: dict = {"credentials": {}, "github": github_data, "pmcs": pmcs, "all_projects": list(sorted(all_projects)), "podlings": server.data.podlings}
    if session and session.credentials:
        prefs['credentials'] = {
            "admin": session.credentials.admin,
            "uid": session.credentials.uid,
            "email": session.credentials.email,
            "fullname": session.credentials.name,
            "github_login": session.credentials.github_login,
            "github_org_member": in_github_org,
        }

    # Logging out??
    if indata.get('logout'):
        # Remove session from memory
        if session.cookie in server.data.sessions:
            del server.data.sessions[session.cookie]
        session.credentials = None

    return prefs


def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
