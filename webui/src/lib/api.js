/*
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
*/

// Thin wrapper around the Boxer JSON API.
//
// Every call is same-origin and relative, so the app keeps working no matter
// which sub-path it is mounted under.

import { INFRA_MAIL } from "./config.js";

export const API_ERROR_MESSAGE =
  "There was a problem contacting the Boxer backend service. Please try again — " +
  `if the problem persists, let ASF Infrastructure know at ${INFRA_MAIL}.`;

/** Raised when the backend is unreachable or answers with something unusable. */
export class ApiError extends Error {
  constructor(message = API_ERROR_MESSAGE, cause = undefined) {
    super(message);
    this.name = "ApiError";
    this.cause = cause;
  }
}

const BASE = {
  mode: "cors",
  cache: "no-cache",
  credentials: "same-origin",
  redirect: "follow",
  referrerPolicy: "no-referrer",
};

async function request(url, init) {
  let response;
  try {
    response = await fetch(url, { ...BASE, ...init });
  } catch (e) {
    if (e?.name === "AbortError") throw e; // caller cancelled, not a failure
    throw new ApiError(API_ERROR_MESSAGE, e);
  }
  let body;
  try {
    body = await response.json();
  } catch (e) {
    throw new ApiError(API_ERROR_MESSAGE, e);
  }
  if (!response.ok) {
    throw new ApiError(body?.message || API_ERROR_MESSAGE);
  }
  return body;
}

/** GET a JSON endpoint. `params` are appended as a query string. */
export function get(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null),
  ).toString();
  return request(qs ? `${path}?${qs}` : path, { method: "GET" });
}

/** POST a JSON body to an endpoint. */
export function post(path, data = {}) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

/* -- Endpoints ------------------------------------------------------------ */

export const api = {
  preferences: () => get("/boxer/api/preferences.json"),
  logout: () => get("/boxer/api/preferences.json", { logout: true }),
  oauth: (formdata) => post("/boxer/api/oauth.json", formdata),
  invite: () => get("/boxer/api/invite.json"),
  unlinkGithub: () => get("/boxer/api/invite.json", { unlink: true }),
  lockAccount: (asfId) => get("/boxer/api/invite.json", { lock: asfId }),
  searchUsers: (query, signal) =>
    request(`/boxer/api/users.json?query=${encodeURIComponent(query)}`, {
      method: "GET",
      signal,
    }),
  saveOptin: (projects) => post("/boxer/api/optin.json", { projects }),
  createRepository: (payload) =>
    post("/boxer/api/repository.json", { action: "create", ...payload }),
  setDefaultBranch: (repository, defaultBranch) =>
    post("/boxer/api/defaultbranch.json", {
      repository,
      default_branch: defaultBranch,
    }),
};
