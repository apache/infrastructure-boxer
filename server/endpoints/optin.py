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
import plugins.projects
import plugins.session

""" Org-visible team listing opt-in endpoint for Boxer"""


async def process(
        server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    if not session.credentials:
        return {
            "okay": False,
            "message": "You need to be logged in to change your team listing preferences.",
        }
    projects = indata.get("projects")
    if not isinstance(projects, list) or not all(isinstance(x, str) for x in projects):
        return {
            "okay": False,
            "message": "Invalid list of projects supplied.",
        }
    for person in server.data.people:
        if person.asf_id == session.credentials.uid:
            eligible = set(x.name for x in person.projects if person in x.committers and x.public_repos)
            ineligible = set(projects) - eligible
            if ineligible:
                return {
                    "okay": False,
                    "message": "You are not a committer on a project with public repositories called: %s"
                               % ", ".join(sorted(ineligible)),
                }
            plugins.projects.save_public_optin(server.database.client, person.asf_id, eligible, projects)
            # Only the projects we offered are in play; anything else this person opted into stays as it was
            current = server.data.public_optin.get(person.asf_id, set())
            server.data.public_optin[person.asf_id] = (current - eligible) | set(projects)
            print(f"Updated team listing opt-in for {person.asf_id}: {', '.join(sorted(projects)) or 'none'}")
            return {
                "okay": True,
                "message": "Your team listing preferences have been saved. It may take a few minutes for the "
                           "changes to show up on GitHub.",
            }
    return {
        "okay": False,
        "message": "Could not find your account in the database!",
    }


def register(server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
