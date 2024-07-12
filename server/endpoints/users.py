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

""" GitHub org admin user search endpoint for Boxer"""


async def process(
        server: plugins.basetypes.Server, session: plugins.session.SessionObject, indata: dict
) -> dict:
    if session.credentials and session.credentials.admin:
        query = indata.get('query', '')
        results = []
        if query:
            for person in server.data.people:
                if (person.github_login and query in person.github_login) or (person.asf_id and query in person.asf_id):
                    results.append({
                        "asf_id": person.asf_id,
                        "github_id": person.github_login,
                        "github_mfa": person.github_mfa,
                        "github_invited": person.github_login in server.data.mfa,
                        "name": person.real_name,
                        "repositories": [x.filename for x in person.repositories]
                    })
                    if len(results) > 10:
                        break
        return {
            "okay": True,
            "results": results,
        }
    else:
        return {
            "okay": False,
            "message": "This endpoint requires administrative access!",
        }


def register(_server: plugins.basetypes.Server):
    return plugins.basetypes.Endpoint(process)
