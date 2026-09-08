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

// Deployment constants for the Boxer front-end.

/** GitHub organisation Boxer manages membership for. */
export const GH_ORG = "apache";

/** OAuth application ID for the "Login with GitHub" step. */
export const GH_CLIENT_ID = "6f70292dcb4d00b5f537";

/** ASF OAuth gateway used for the initial (Apache ID) login. */
export const ASF_OAUTH_URL = "https://oauth.apache.org/auth";

/** Where users go for help. */
export const INFRA_CONTACT = "https://infra.apache.org/contact.html";
export const INFRA_MAIL = "users@infra.apache.org";

/** Random, per-page-load OAuth state token. */
export const OAUTH_STATE = Array.from({ length: 3 }, () =>
  Math.random().toString(20).slice(2, 8),
).join("");

/**
 * Absolute URL of the app itself (e.g. https://gitbox.apache.org/boxer/).
 * Both OAuth providers redirect back here, so it must not contain a query
 * string or fragment.
 */
export function appUrl() {
  return `${location.origin}${location.pathname}`;
}

/** Send the browser off to the ASF OAuth gateway. */
export function beginAsfOauth() {
  const redirect = encodeURIComponent(
    `${appUrl()}?action=oauth&state=${OAUTH_STATE}`,
  );
  location.href = `${ASF_OAUTH_URL}?redirect_uri=${redirect}&state=${OAUTH_STATE}`;
}

/** Send the browser off to GitHub's OAuth gateway. */
export function beginGithubOauth() {
  const redirect = encodeURIComponent(
    `${appUrl()}?action=oauth&key=github&state=${OAUTH_STATE}`,
  );
  location.href = `https://github.com/login/oauth/authorize?client_id=${GH_CLIENT_ID}&redirect_uri=${redirect}`;
}

/** Canonical web URLs for a repository. */
export function githubUrl(repo) {
  return `https://github.com/${GH_ORG}/${repo}`;
}

export function gitboxUrl(repo, isPrivate) {
  if (isPrivate) {
    const m = repo.match(/^(?:incubator-)?(empire-db|[^-.]+)-?.*/);
    if (m) return `https://gitbox.apache.org/repos/private/${m[1]}/${repo}.git`;
  }
  return `https://gitbox.apache.org/repos/asf/${repo}.git`;
}
