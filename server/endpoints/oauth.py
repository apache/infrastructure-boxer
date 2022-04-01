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

"""Parent OAuth endpoint for ASF Infra Boxer"""

import plugins.basetypes
import plugins.session
import plugins.oauthGeneric
import plugins.oauthGithub
import plugins.projects
import typing
import aiohttp.web
import hashlib


async def process(
    server: plugins.basetypes.Server,
    session: plugins.session.SessionObject,
    indata: dict,
) -> typing.Union[dict, aiohttp.web.Response]:

    state = indata.get("state")
    code = indata.get("code")

    rv: typing.Optional[dict] = None
    oatype = None
    # GitHub OAuth - Fetches name and email
    if indata.get('key', '') == 'github' and code:
        rv = await plugins.oauthGithub.process(indata, session, server)
        oatype = "github"

    # Generic OAuth handler, only one we support for now. Works with ASF OAuth.
    elif state and code:
        rv = await plugins.oauthGeneric.process(indata, session, server)
        oatype = "apache"

    if rv and oatype == "apache":
        ghid = None
        person = plugins.projects.Committer(asf_id=rv["uid"], linkdb=server.database.client)
        if person and person.github_login:
            ghid = person.github_login
            if person not in server.data.people:
                server.data.people.append(person)
        is_admin = person.asf_id in server.config.oauth.admins
        is_member = rv.get("isMember", False)
        cookie = await plugins.session.set_session(server, uid=rv["uid"], name=rv["fullname"], email=rv["email"], github_login=ghid, admin=is_admin, member=is_member)
        return aiohttp.web.Response(
            headers={"set-cookie": cookie, "content-type": "application/json"}, status=200, text='{"okay": true}',
        )
    elif rv and oatype == "github" and session.credentials:
        session.credentials.github_login = rv["login"]
        session.credentials.github_id = rv["id"]

        if session.credentials.uid in server.data.people:
            print(f"Removing stale GitHub link entry for {session.credentials.uid}")
            server.data.people.remove(session.credentials.uid)

        person = plugins.projects.Committer(
            asf_id=session.credentials.uid,
            linkdb=server.database.client,
        )
        person.github_login = session.credentials.github_login
        person.github_id = session.credentials.github_id
        person.real_name = session.credentials.name
        person.github_mfa = session.credentials.github_login in server.data.mfa and server.data.mfa[session.credentials.github_login]
        person.save(server.database.client)
        server.data.people.append(person)
        return {
            "okay": True,
            "message": f"Authed as {session.credentials.github_login}"
        }
    return {"okay": False, "message": "Could not process OAuth login!"}


def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
