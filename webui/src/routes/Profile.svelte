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
  import Icon from "../components/Icon.svelte";
  import Notice from "../components/Notice.svelte";
  import Stepper from "../components/Stepper.svelte";
  import RepoTable from "../components/RepoTable.svelte";
  import Spinner from "../components/Spinner.svelte";
  import { untrack } from "svelte";
  import { api } from "../lib/api.js";
  import { GH_ORG } from "../lib/config.js";
  import { alert as showAlert, confirm as showConfirm } from "../lib/dialogs.js";

  let { prefs } = $props();

  const credentials = $derived(prefs.credentials ?? {});
  const github = $derived(prefs.github ?? {});
  const hasRepos = $derived((github.repositories ?? []).length > 0);

  /* -- Unlinking ---------------------------------------------------------- */

  let unlinking = $state(false);

  async function unlinkGithub() {
    const ok = await showConfirm({
      title: "Unlink your GitHub account?",
      body:
        "You will lose all GitHub write access on your current account. You can " +
        "link this or another GitHub account again afterwards.",
      confirmLabel: "Unlink account",
      danger: true,
    });
    if (!ok) return;
    unlinking = true;
    try {
      await api.unlinkGithub();
      await showAlert({
        title: "GitHub account unlinked",
        body:
          "Please authenticate again to link a new or previous GitHub account.",
      });
      location.reload();
    } catch (e) {
      unlinking = false;
      await showAlert({ title: "Could not unlink", body: e.message });
    }
  }

  /* -- Team listing opt-in ------------------------------------------------ */

  const projects = $derived(prefs.projects ?? []);
  let selected = $state(new Set(untrack(() => prefs.public_optin) ?? []));
  let saving = $state(false);
  let saveResult = $state(null);

  function toggleProject(project, checked) {
    const next = new Set(selected);
    if (checked) next.add(project);
    else next.delete(project);
    selected = next;
    saveResult = null;
  }

  async function saveOptin() {
    saving = true;
    saveResult = null;
    try {
      const rv = await api.saveOptin([...selected]);
      saveResult = { tone: rv.okay ? "success" : "danger", message: rv.message };
    } catch (e) {
      saveResult = {
        tone: "danger",
        message:
          "Something went wrong while saving your preferences. Reload this page " +
          "to check which projects you are currently listed in.",
      };
    } finally {
      saving = false;
    }
  }
</script>

<div class="stack">
  <Stepper completed={github.mfa ? 5 : 3} />

  <section class="identity card">
    <div class="identity-main">
      {#if github.login}
        <img
          class="avatar"
          src={`https://github.com/${github.login}.png?size=160`}
          alt=""
          width="80"
          height="80"
        />
      {:else}
        <span class="avatar avatar-fallback"><Icon name="user" size={34} /></span>
      {/if}

      <div class="identity-copy">
        <h1>{credentials.fullname || credentials.uid}</h1>
        <div class="chips">
          {#if credentials.admin}
            <span class="badge badge-accent">Infrastructure admin</span>
          {/if}
          {#if credentials.tooling}
            <span class="badge badge-accent">Tooling</span>
          {/if}
          {#if github.mfa}
            <span class="badge badge-success"><Icon name="lock" size={12} /> MFA enabled</span>
          {:else}
            <span class="badge badge-warn"><Icon name="alert" size={12} /> MFA missing</span>
          {/if}
          {#if credentials.github_org_member}
            <span class="badge badge-success">
              <Icon name="users" size={12} /> {GH_ORG} org member
            </span>
          {/if}
        </div>
      </div>
    </div>

    <dl class="accounts">
      <div class="account">
        <dt><img src="./images/asf.png" alt="" width="14" height="21" /> Apache</dt>
        <dd>
          <span class="mono">{credentials.uid}</span>
          {#if credentials.email}
            <span class="faint small">{credentials.email}</span>
          {/if}
        </dd>
      </div>
      {#if github.login}
        <div class="account">
          <dt><Icon name="github" size={15} /> GitHub</dt>
          <dd>
            <a
              class="mono"
              href={`https://github.com/${github.login}`}
              target="_blank"
              rel="noopener noreferrer">{github.login}</a
            >
            <button
              class="link-button unlink"
              type="button"
              onclick={unlinkGithub}
              disabled={unlinking}
            >
              {unlinking ? "unlinking…" : "unlink account"}
            </button>
          </dd>
        </div>
      {/if}
    </dl>
  </section>

  {#if !github.mfa}
    <Notice tone="warn" title="Multi-factor authentication is required">
      <p>
        Enable MFA on your GitHub account to receive write access to Apache
        repositories. Set it up under
        <a href="https://github.com/settings/security" target="_blank" rel="noopener noreferrer">
          GitHub account security</a
        >; it can take up to five minutes for Boxer to notice the change.
      </p>
    </Notice>
  {:else if hasRepos}
    <RepoTable {github} />
  {:else}
    <Notice tone="info" title="No repository access yet">
      <p>
        You do not appear to have write access to any git repositories right now.
        If you have just linked your accounts, allow a few minutes for the system
        to register your repository list.
      </p>
    </Notice>
  {/if}

  {#if projects.length > 0}
    <section class="card">
      <div class="card-head">
        <div>
          <h2>Project team listing</h2>
          <p class="sub">Choose which project teams list you on GitHub.</p>
        </div>
      </div>
      <div class="card-body">
        <p class="prose muted">
          Which projects you work on is personal information, so we only list it
          if you ask us to. Ticking a project adds you to its GitHub team, which
          is visible to members of the <span class="mono">{GH_ORG}</span> GitHub
          organisation — not to the wider internet. These teams exist so they can
          be named as approvers on GitHub Actions deployment environments. Untick
          a project to be removed from its team again.
        </p>

        <ul class="optin">
          {#each projects as project (project)}
            <li>
              <label class="checkbox">
                <input
                  type="checkbox"
                  checked={selected.has(project)}
                  onchange={(e) => toggleProject(project, e.currentTarget.checked)}
                />
                <span class="optin-label">
                  <strong>{project}</strong>
                  <span class="faint small mono">{GH_ORG}/{project}-public</span>
                </span>
              </label>
            </li>
          {/each}
        </ul>
      </div>
      <div class="card-foot">
        <button class="btn btn-primary" type="button" onclick={saveOptin} disabled={saving}>
          {#if saving}<Spinner size={14} />{/if}
          {saving ? "Saving…" : "Save team listing preferences"}
        </button>
        {#if saveResult}
          <span class="save-result" class:error={saveResult.tone === "danger"}>
            <Icon name={saveResult.tone === "danger" ? "alert" : "check"} size={15} />
            {saveResult.message}
          </span>
        {/if}
      </div>
    </section>
  {/if}
</div>

<style>
  .identity {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 28px;
    flex-wrap: wrap;
    padding: 22px 24px;
    background: linear-gradient(
      135deg,
      color-mix(in srgb, var(--accent) 9%, var(--surface)),
      var(--surface) 55%
    );
  }

  .identity-main {
    display: flex;
    align-items: center;
    gap: 18px;
    min-width: 0;
  }

  .avatar {
    width: 80px;
    height: 80px;
    flex: none;
    border: 3px solid var(--surface);
    border-radius: 50%;
    background: var(--surface-2);
    box-shadow: var(--shadow-sm);
    object-fit: cover;
  }

  .avatar-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-faint);
  }

  .identity-copy h1 {
    margin: 0 0 8px;
    font-size: 1.5rem;
  }

  .chips {
    display: flex;
    gap: 7px;
    flex-wrap: wrap;
  }

  .accounts {
    display: grid;
    gap: 10px;
    margin: 0;
  }

  .account dt {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.72rem;
    font-weight: 650;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .account dd {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin: 2px 0 0 23px;
    font-size: 0.92rem;
  }

  .unlink {
    font-size: 0.78rem;
    color: var(--text-faint);
  }

  .unlink:hover {
    color: var(--danger);
  }

  .optin {
    display: grid;
    gap: 2px;
    max-width: 620px;
    margin: 4px 0 0;
    padding: 0;
    list-style: none;
  }

  .optin li {
    border-radius: var(--radius-sm);
  }

  .optin li:hover {
    background: var(--surface-2);
  }

  .optin .checkbox {
    padding: 8px 10px;
  }

  .optin-label {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }

  .save-result {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    color: var(--success);
    font-size: 0.87rem;
  }

  .save-result.error {
    color: var(--danger);
  }

  @media (max-width: 640px) {
    .identity {
      padding: 18px;
    }

    .avatar {
      width: 60px;
      height: 60px;
    }
  }
</style>
