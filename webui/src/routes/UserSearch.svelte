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
  import { untrack } from "svelte";
  import Icon from "../components/Icon.svelte";
  import Notice from "../components/Notice.svelte";
  import Spinner from "../components/Spinner.svelte";
  import { api } from "../lib/api.js";
  import { replaceQuery } from "../lib/router.js";
  import { GH_ORG } from "../lib/config.js";
  import { alert as showAlert, confirm as showConfirm } from "../lib/dialogs.js";

  let { prefs, initialQuery = "" } = $props();

  const isAdmin = $derived(Boolean(prefs?.credentials?.admin));

  const DEBOUNCE_MS = 250;

  let query = $state(untrack(() => initialQuery));
  let results = $state([]);
  let searching = $state(false);
  let searched = $state(false);
  let errorMessage = $state("");

  let timer = null;
  let inflight = null;

  /** Diagnose a search result the same way the old admin view did. */
  function statusOf(user) {
    if (!user.github_id) {
      return { note: 1, tone: "warn", label: "Not authenticated on GitHub" };
    }
    if (!user.github_invited) {
      return { note: 2, tone: "warn", label: `Not in the ${GH_ORG} org` };
    }
    if (!user.github_mfa) {
      return { note: 3, tone: "danger", label: "MFA not enabled" };
    }
    return { note: 0, tone: "success", label: "Accounts linked" };
  }

  async function runSearch(value) {
    inflight?.abort();
    if (!value) {
      results = [];
      searched = false;
      searching = false;
      return;
    }
    const controller = new AbortController();
    inflight = controller;
    searching = true;
    errorMessage = "";
    try {
      const rv = await api.searchUsers(value, controller.signal);
      results = rv.results ?? [];
      searched = true;
    } catch (e) {
      if (e?.name === "AbortError") return;
      errorMessage = e.message;
      results = [];
    } finally {
      if (inflight === controller) {
        inflight = null;
        searching = false;
      }
    }
  }

  function onInput(value) {
    query = value;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      const trimmed = query.trim();
      replaceQuery("search", trimmed ? { query: trimmed } : {});
      runSearch(trimmed);
    }, DEBOUNCE_MS);
  }

  async function lockAccount(user) {
    const ok = await showConfirm({
      title: `Lock ${user.asf_id}?`,
      body:
        `This unlinks ${user.asf_id} from GitHub and removes the account from ` +
        "the Boxer database. The user has to authenticate again from scratch.",
      confirmLabel: "Lock and unlink",
      danger: true,
    });
    if (!ok) return;
    try {
      const rv = await api.lockAccount(user.asf_id);
      await showAlert({
        title: rv.okay ? "Account locked" : "Could not lock the account",
        body: rv.okay
          ? `${user.asf_id} has been locked and unlinked from GitHub.`
          : rv.message,
      });
      if (rv.okay) runSearch(query.trim());
    } catch (e) {
      await showAlert({ title: "Could not lock the account", body: e.message });
    }
  }

  // Kick off the search for a URL that already carried ?query=...
  $effect(() => {
    const seed = untrack(() => initialQuery);
    if (seed) runSearch(seed.trim());
    return () => {
      window.clearTimeout(timer);
      inflight?.abort();
    };
  });

  const legend = [
    { note: 0, text: "Accounts linked — all is well, nothing to do here." },
    {
      note: 1,
      text:
        "Not authenticated on GitHub — the user exists in LDAP but has not used Boxer " +
        "to authenticate with GitHub yet, so we do not know their GitHub login. They " +
        "should run through the Boxer setup steps.",
    },
    {
      note: 2,
      text:
        `Not in the ${GH_ORG} org — the ASF and GitHub OAuth steps are done, but the ` +
        `user has not been invited to the organisation or has not accepted the ` +
        `invitation. Point them at https://github.com/orgs/${GH_ORG}/invitation.`,
    },
    {
      note: 3,
      text:
        "MFA not enabled — the user is in the organisation but has not enabled " +
        "multi-factor authentication, which is required for write access.",
    },
  ];
</script>

<div class="page-head">
  <h1>User search</h1>
  <p class="lede">
    Look up an Apache or GitHub ID to see a user's link status and access level.
  </p>
</div>

{#if !isAdmin}
  <Notice tone="danger" title="Administrative access required">
    <p>This page is only available to ASF Infrastructure administrators.</p>
  </Notice>
{:else}
  <div class="layout">
    <div class="searchbar">
      <Icon name="search" size={17} />
      <input
        type="search"
        value={query}
        oninput={(e) => onInput(e.currentTarget.value)}
        placeholder="Enter an Apache or GitHub ID"
        aria-label="Search for a user"
        spellcheck="false"
        autocapitalize="none"
      />
      {#if searching}<Spinner size={16} />{/if}
    </div>

    {#if errorMessage}
      <Notice tone="danger" title="Search failed"><p>{errorMessage}</p></Notice>
    {:else if searched && results.length === 0}
      <Notice tone="info">
        <p>No users matching “{query}” could be found.</p>
      </Notice>
    {:else if results.length > 0}
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th scope="col">Apache ID</th>
              <th scope="col">Name</th>
              <th scope="col">GitHub ID</th>
              <th scope="col" class="center">MFA</th>
              <th scope="col" class="right">Repos</th>
              <th scope="col">Status</th>
              <th scope="col" class="right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {#each results as user (user.asf_id)}
              {@const status = statusOf(user)}
              <tr>
                <td class="mono strong">{user.asf_id}</td>
                <td class="muted">{user.name || "—"}</td>
                <td>
                  {#if user.github_id}
                    <a
                      class="mono"
                      href={`https://github.com/${user.github_id}`}
                      target="_blank"
                      rel="noopener noreferrer">{user.github_id}</a
                    >
                  {:else}
                    <span class="faint">—</span>
                  {/if}
                </td>
                <td class="center">
                  {#if user.github_mfa}
                    <span class="mfa on" title="MFA enabled"><Icon name="lock" size={14} /></span>
                  {:else}
                    <span class="mfa off" title="MFA not enabled"><Icon name="alert" size={14} /></span>
                  {/if}
                </td>
                <td class="right mono">{user.repositories?.length ?? 0}</td>
                <td>
                  <span class={`badge badge-${status.tone}`}>{status.label}</span>
                  <sup class="faint">[{status.note}]</sup>
                </td>
                <td class="right">
                  <button class="btn btn-sm btn-danger" type="button" onclick={() => lockAccount(user)}>
                    <Icon name="unlink" size={13} /> Lock account
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="faint small">The backend returns at most ten matches per query.</p>
    {/if}

    <section class="card">
      <div class="card-head"><h2>What the statuses mean</h2></div>
      <div class="card-body">
        <dl class="legend">
          {#each legend as item (item.note)}
            <div>
              <dt>[{item.note}]</dt>
              <dd>{item.text}</dd>
            </div>
          {/each}
        </dl>
      </div>
    </section>
  </div>
{/if}

<style>
  .layout {
    display: grid;
    gap: 20px;
  }

  .searchbar {
    display: flex;
    align-items: center;
    gap: 10px;
    max-width: 520px;
    padding: 2px 14px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--text-faint);
    box-shadow: var(--shadow-sm);
  }

  .searchbar:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent);
  }

  .searchbar input {
    flex: 1;
    padding: 10px 0;
    border: 0;
    background: none;
    color: var(--text);
    font-size: 0.95rem;
  }

  .searchbar input:focus {
    outline: none;
    box-shadow: none;
  }

  .strong {
    font-weight: 600;
  }

  .center {
    text-align: center;
  }

  .right {
    text-align: right;
  }

  .mfa {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
  }

  .mfa.on {
    background: var(--success-soft);
    color: var(--success);
  }

  .mfa.off {
    background: var(--danger-soft);
    color: var(--danger);
  }

  .legend {
    display: grid;
    gap: 10px;
    margin: 0;
    font-size: 0.88rem;
  }

  .legend > div {
    display: flex;
    gap: 12px;
  }

  .legend dt {
    flex: none;
    width: 28px;
    color: var(--text-faint);
    font-family: var(--font-mono);
  }

  .legend dd {
    margin: 0;
    color: var(--text-muted);
  }
</style>
