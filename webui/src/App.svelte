<!--
Licensed to the Apache Software Foundation (ASF) under one or more contributor
license agreements. See the NOTICE file distributed with this work for
additional information regarding copyright ownership. The ASF licenses this
file to you under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy of
the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations under
the License.
-->
<script>
  import AppHeader from "./components/AppHeader.svelte";
  import AppFooter from "./components/AppFooter.svelte";
  import DialogHost from "./components/DialogHost.svelte";
  import Notice from "./components/Notice.svelte";
  import Spinner from "./components/Spinner.svelte";
  import Icon from "./components/Icon.svelte";

  import Profile from "./routes/Profile.svelte";
  import GithubAuth from "./routes/GithubAuth.svelte";
  import GithubOrg from "./routes/GithubOrg.svelte";
  import MfaCheck from "./routes/MfaCheck.svelte";
  import NewRepo from "./routes/NewRepo.svelte";
  import DefaultBranch from "./routes/DefaultBranch.svelte";
  import UserSearch from "./routes/UserSearch.svelte";
  import Faq from "./routes/Faq.svelte";

  import { api } from "./lib/api.js";
  import { appUrl, beginAsfOauth } from "./lib/config.js";
  import { queryParams, route, href, link } from "./lib/router.js";

  /**
   * Boot state:
   *   "loading"  - fetching preferences
   *   "oauth"    - completing an OAuth round trip
   *   "ready"    - preferences loaded, render a page
   *   "error"    - the backend could not be reached
   */
  let status = $state("loading");
  let prefs = $state(null);
  let errorMessage = $state("");

  /** Port of the old prime(): work out who the visitor is before rendering. */
  async function boot() {
    const formdata = queryParams();

    try {
      prefs = await api.preferences();
    } catch (e) {
      status = "error";
      errorMessage = e.message;
      return;
    }

    // An OAuth provider just sent the user back here; finish the handshake
    // before looking at the session.
    if (formdata.action === "oauth") {
      status = "oauth";
      try {
        const rv = await api.oauth(formdata);
        if (rv.okay) {
          location.href = appUrl();
          return;
        }
        status = "error";
        errorMessage =
          rv.message || "The login could not be completed. Please try again.";
      } catch (e) {
        status = "error";
        errorMessage = e.message;
      }
      return;
    }

    // Not logged in at the ASF yet: off to the OAuth gateway.
    if (!prefs?.credentials?.uid) {
      status = "oauth";
      beginAsfOauth();
      return;
    }

    status = "ready";
  }

  boot();

  async function logout() {
    try {
      await api.logout();
    } catch {
      // Even if the call fails, drop the user back at the front page.
    }
    location.href = appUrl();
  }

  /**
   * Which page to show. The account page doubles as the onboarding flow: a
   * visitor who has not linked GitHub, joined the org or enabled MFA is shown
   * the step they are stuck on instead.
   */
  const view = $derived.by(() => {
    const action = $route.action || "preferences";
    if (action === "faq") return "faq";
    if (action === "verify") return "github-auth";
    if (action === "search") return "search";
    if (action === "newrepo") return "newrepo";
    if (action === "defaultbranch") return "defaultbranch";
    if (action !== "preferences") return "unknown";
    if (!prefs?.github?.login) return "github-auth";
    if (!prefs?.credentials?.github_org_member) return "github-org";
    if (!prefs?.github?.mfa) return "mfa";
    return "profile";
  });
</script>

<AppHeader {prefs} onLogout={logout} />

<main class="page">
  <div class="container">
    {#if status === "loading"}
      <Spinner block label="Loading your Boxer account…" size={26} />
    {:else if status === "oauth"}
      <Spinner block label="Signing you in…" size={26} />
    {:else if status === "error"}
      <div class="boot-error">
        <Notice tone="danger" title="Boxer is not answering">
          <p>{errorMessage}</p>
        </Notice>
        <button class="btn" type="button" onclick={() => location.reload()}>
          Try again
        </button>
      </div>
    {:else if view === "profile"}
      <Profile {prefs} />
    {:else if view === "github-auth"}
      <GithubAuth {prefs} />
    {:else if view === "github-org"}
      <GithubOrg />
    {:else if view === "mfa"}
      <MfaCheck />
    {:else if view === "newrepo"}
      <NewRepo {prefs} />
    {:else if view === "defaultbranch"}
      <DefaultBranch {prefs} />
    {:else if view === "search"}
      <UserSearch {prefs} initialQuery={$route.params.query ?? ""} />
    {:else if view === "faq"}
      <Faq />
    {:else}
      <div class="notfound">
        <Icon name="help" size={34} />
        <h1>That page does not exist</h1>
        <p class="muted">
          Boxer has no action called “{$route.action}”.
        </p>
        <a class="btn btn-primary" href={href("")} use:link>Back to your account</a>
      </div>
    {/if}
  </div>
</main>

<DialogHost />
<AppFooter />

<style>
  .boot-error {
    display: grid;
    gap: 16px;
    justify-items: start;
    max-width: 620px;
    margin: 40px auto;
  }

  .notfound {
    display: grid;
    gap: 6px;
    justify-items: center;
    padding: 60px 0;
    color: var(--text-faint);
    text-align: center;
  }

  .notfound h1 {
    margin: 10px 0 0;
    color: var(--text);
  }

  .notfound .btn {
    margin-top: 14px;
  }
</style>
