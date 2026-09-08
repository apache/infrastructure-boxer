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
  import Spinner from "../components/Spinner.svelte";
  import { api } from "../lib/api.js";
  import { GH_ORG, githubUrl, gitboxUrl } from "../lib/config.js";
  import { confirm as showConfirm } from "../lib/dialogs.js";

  let { prefs } = $props();

  const credentials = $derived(prefs.credentials ?? {});
  const mayCreatePrivate = $derived(
    Boolean(credentials.admin || credentials.tooling),
  );
  const allProjects = $derived(prefs.all_projects ?? []);
  const podlings = $derived(prefs.podlings ?? []);
  const myPmcs = $derived(prefs.pmcs ?? []);

  let project = $state("");
  let suffix = $state("");
  let incubatorPrefix = $state(true);
  let terraformPrefix = $state(false);
  let isPrivate = $state(false);
  let commitList = $state("");
  let devList = $state("");

  let submitting = $state(false);
  let created = $state(null);
  let apiError = $state("");

  const isPodling = $derived(podlings.includes(project));

  /** Which projects this user may create repositories for. */
  function mayCreateFor(name) {
    return Boolean(credentials.admin) || myPmcs.includes(name);
  }

  function onProjectChange() {
    // Pre-fill the mailing list targets the way the project usually names them.
    commitList = project ? `commits@${project}.apache.org` : "";
    devList = project ? `dev@${project}.apache.org` : "";
  }

  const suffixValid = $derived(/^[-a-z0-9]*$/.test(suffix));

  /** The name the backend will actually create, or null if the form is not ready. */
  const repoName = $derived.by(() => {
    if (!project || !suffixValid) return null;
    let base = project;
    if (terraformPrefix) base = `terraform-provider-${project}`;
    else if (isPodling && incubatorPrefix) base = `incubator-${project}`;
    return suffix ? `${base}-${suffix}` : base;
  });

  const validationMessage = $derived.by(() => {
    if (!project) return "Select a project to continue.";
    if (!suffixValid)
      return "Invalid repository sub-name: lowercase letters, digits and dashes only.";
    return null;
  });

  async function submit() {
    if (!repoName) return;
    const fullName = `${repoName}.git`;

    let ok = await showConfirm({
      title: "Create this repository?",
      body: `This will create ${fullName} on GitHub and GitBox.`,
      confirmLabel: "Create repository",
    });
    if (!ok) return;

    // INFRA-26130: catch names like openserverless-openserverless-foo.git
    if (suffix && suffix.startsWith(project)) {
      ok = await showConfirm({
        title: "That name repeats the project",
        body: `${fullName} contains the project name twice. Are you sure that is what you want?`,
        confirmLabel: "Yes, create it",
        danger: true,
      });
      if (!ok) return;
    }

    submitting = true;
    apiError = "";
    try {
      const rv = await api.createRepository({
        repository: fullName,
        private: isPrivate,
        title: `Apache ${project}`,
        commit: commitList,
        issue: devList,
      });
      if (rv.okay) {
        created = {
          name: repoName,
          github: githubUrl(repoName),
          gitbox: gitboxUrl(repoName, isPrivate),
        };
      } else {
        apiError = rv.message || "The repository could not be created.";
      }
    } catch (e) {
      apiError = e.message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="page-head">
  <h1>Create a repository</h1>
  <p class="lede">
    Sets up a new git repository on GitBox and mirrors it to the
    <span class="mono">{GH_ORG}</span> organisation on GitHub.
  </p>
</div>

{#if created}
  <section class="card">
    <div class="card-body stack">
      <Notice tone="success" title={`${created.name}.git has been created`}>
        <p>
          The repository will be ready for use within a few minutes. User
          permissions are usually applied within five minutes — if they are not,
          let us know at <a href="mailto:users@infra.apache.org">users@infra.apache.org</a>.
        </p>
      </Notice>

      <ul class="result-links">
        <li>
          <Icon name="branch" size={16} />
          <a href={created.gitbox} target="_blank" rel="noopener noreferrer">{created.gitbox}</a>
        </li>
        <li>
          <Icon name="github" size={16} />
          <a href={created.github} target="_blank" rel="noopener noreferrer">{created.github}</a>
        </li>
      </ul>

      <p class="muted small">
        Fine-tune notification targets, branch protection and more with
        <a href="https://s.apache.org/asfyaml" target="_blank" rel="noopener noreferrer">.asf.yaml</a>
        in the repository's main branch.
      </p>
    </div>
    <div class="card-foot">
      <button class="btn" type="button" onclick={() => (created = null)}>
        Create another repository
      </button>
    </div>
  </section>
{:else}
  <div class="layout">
    <div class="form-column">
    <section class="card">
      <div class="card-head"><h2>Repository details</h2></div>
      <div class="card-body">
        <div class="field">
          <label for="project">Project</label>
          <select id="project" bind:value={project} onchange={onProjectChange}>
            <option value="">— Select a project —</option>
            {#each allProjects as name (name)}
              <option value={name} disabled={!mayCreateFor(name)}>{name}</option>
            {/each}
          </select>
          <span class="hint">
            Only projects whose (P)PMC you are a member of can be selected.
          </span>
        </div>

        <div class="field">
          <label for="suffix">Repository sub-name <span class="faint">(optional)</span></label>
          <input
            id="suffix"
            type="text"
            bind:value={suffix}
            placeholder="e.g. site, docs, client-go"
            spellcheck="false"
            autocapitalize="none"
            aria-invalid={!suffixValid}
          />
          <span class="hint">
            Appended to the project name. Lowercase letters, digits and dashes only.
          </span>
        </div>

        {#if isPodling}
          <label class="checkbox toggle">
            <input type="checkbox" bind:checked={incubatorPrefix} />
            <span>
              <strong>Include the <span class="mono">incubator-</span> prefix</strong>
              <span class="hint">Standard for podlings that have not graduated yet.</span>
            </span>
          </label>
        {/if}

        <label class="checkbox toggle">
          <input type="checkbox" bind:checked={terraformPrefix} />
          <span>
            <strong>Terraform provider repository</strong>
            <span class="hint">
              Adds the <span class="mono">terraform-provider-</span> prefix HashiCorp
              requires (INFRA-27355). Replaces the incubator prefix when both apply.
            </span>
          </span>
        </label>

        {#if mayCreatePrivate}
          <label class="checkbox toggle">
            <input type="checkbox" bind:checked={isPrivate} />
            <span>
              <strong class="danger-text">Make the repository private</strong>
              <span class="hint">
                Private repositories are visible only to the (P)PMC of the project,
                on both GitBox and GitHub.
              </span>
            </span>
          </label>
        {/if}
      </div>
    </section>

    <section class="card">
      <div class="card-head"><h2>Notifications</h2></div>
      <div class="card-body">
        <div class="field">
          <label for="commit">Commit mailing list</label>
          <input id="commit" type="text" bind:value={commitList} spellcheck="false" />
        </div>
        <div class="field">
          <label for="dev">Issue and pull request mailing list</label>
          <input id="dev" type="text" bind:value={devList} spellcheck="false" />
        </div>
        <p class="hint">
          Both must be existing apache.org lists. You can change these later with
          <a href="https://s.apache.org/asfyaml" target="_blank" rel="noopener noreferrer">.asf.yaml</a>.
        </p>
      </div>
    </section>
    </div>

    <section class="card summary">
      <div class="card-body">
        <span class="summary-label">Repository to be created</span>
        {#if repoName}
          <p class="summary-name mono">
            {repoName}.git
            {#if isPrivate}<span class="badge badge-danger">private</span>{/if}
          </p>
          <p class="summary-urls small muted">
            {gitboxUrl(repoName, isPrivate)}<br />
            {githubUrl(repoName)}
          </p>
        {:else}
          <p class="summary-pending">{validationMessage}</p>
        {/if}
      </div>
      <div class="card-foot">
        <button
          class="btn btn-primary"
          type="button"
          onclick={submit}
          disabled={!repoName || submitting}
        >
          {#if submitting}<Spinner size={14} />{/if}
          {submitting ? "Creating…" : "Create repository"}
        </button>
        {#if validationMessage && project}
          <span class="small danger-text">{validationMessage}</span>
        {/if}
      </div>
    </section>

    {#if apiError}
      <div class="error-row">
        <Notice tone="danger" title="The repository could not be created">
          <p>{apiError}</p>
        </Notice>
      </div>
    {/if}
  </div>
{/if}

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    align-items: start;
    gap: 20px;
    max-width: 1040px;
  }

  .form-column {
    display: grid;
    gap: 20px;
    min-width: 0;
  }

  .summary {
    position: sticky;
    top: calc(var(--header-height) + 24px);
  }

  @media (max-width: 900px) {
    .layout {
      grid-template-columns: minmax(0, 1fr);
    }

    .summary {
      position: static;
    }
  }

  .toggle {
    align-items: flex-start;
    padding: 12px 14px;
    margin-bottom: 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-2);
  }

  .toggle input {
    margin-top: 3px;
  }

  .toggle > span {
    display: block;
  }

  .toggle .hint {
    display: block;
    margin-top: 2px;
    font-size: 0.82rem;
    font-weight: 400;
    color: var(--text-muted);
  }

  .card.summary {
    border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
  }

  .summary-label {
    display: block;
    margin-bottom: 6px;
    font-size: 0.72rem;
    font-weight: 650;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-muted);
  }

  .summary-name {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    font-size: 1.15rem;
    font-weight: 600;
  }

  .summary-urls {
    margin: 8px 0 0;
    line-height: 1.6;
  }

  .summary-pending {
    margin: 0;
    color: var(--text-muted);
  }

  .danger-text {
    color: var(--danger);
  }

  .error-row {
    grid-column: 1 / -1;
  }

  .result-links {
    display: grid;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .result-links li {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-muted);
  }
</style>
