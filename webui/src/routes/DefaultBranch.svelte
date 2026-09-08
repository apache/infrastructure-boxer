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
  import Notice from "../components/Notice.svelte";
  import Spinner from "../components/Spinner.svelte";
  import { api } from "../lib/api.js";

  let { prefs } = $props();

  const repositories = $derived(
    [...(prefs.github?.repositories ?? [])].sort((a, b) => a.localeCompare(b)),
  );

  let repository = $state("");
  let branch = $state("");
  let submitting = $state(false);
  let result = $state(null);

  // Same rule the backend enforces: a git branch name, at most 39 characters.
  const branchValid = $derived(/^[a-z]+[a-z0-9./_-]{0,38}$/i.test(branch));
  const ready = $derived(Boolean(repository) && branchValid);

  async function submit() {
    if (!ready) return;
    submitting = true;
    result = null;
    try {
      const rv = await api.setDefaultBranch(repository, branch);
      result = {
        tone: rv.okay ? "success" : "danger",
        title: rv.okay ? "Default branch changed" : "Could not change the default branch",
        message: rv.okay
          ? `${repository} now defaults to ${branch}.`
          : rv.message,
      };
    } catch (e) {
      result = {
        tone: "danger",
        title: "Could not change the default branch",
        message: e.message,
      };
    } finally {
      submitting = false;
    }
  }
</script>

<div class="page-head">
  <h1>Change default branch</h1>
  <p class="lede">
    Points a repository at a different existing branch. Only (I)PMC members of
    the owning project may change a repository's default branch.
  </p>
</div>

<div class="layout">
  <section class="card">
    <div class="card-body">
      <div class="field">
        <label for="repository">Repository</label>
        <select id="repository" bind:value={repository}>
          <option value="">— Select a repository —</option>
          {#each repositories as repo (repo)}
            <option value={repo}>{repo}</option>
          {/each}
        </select>
        <span class="hint">Only repositories you can write to are listed.</span>
      </div>

      <div class="field">
        <label for="branch">New default branch</label>
        <input
          id="branch"
          type="text"
          bind:value={branch}
          placeholder="main"
          spellcheck="false"
          autocapitalize="none"
          aria-invalid={Boolean(branch) && !branchValid}
        />
        <span class="hint">
          The branch must already exist. Enter the bare branch name — no
          <span class="mono">refs/heads/</span> prefix.
        </span>
        {#if branch && !branchValid}
          <span class="hint error">
            “{branch}” is not a valid branch name. It must follow standard git
            branch naming and be at most 39 characters.
          </span>
        {/if}
      </div>
    </div>
    <div class="card-foot">
      <button class="btn btn-primary" type="button" onclick={submit} disabled={!ready || submitting}>
        {#if submitting}<Spinner size={14} />{/if}
        {submitting ? "Submitting…" : "Change default branch"}
      </button>
    </div>
  </section>

  {#if result}
    <Notice tone={result.tone} title={result.title}>
      <p>{result.message}</p>
    </Notice>
  {/if}
</div>

<style>
  .layout {
    display: grid;
    gap: 20px;
    max-width: 620px;
  }

  .hint.error {
    color: var(--danger);
  }
</style>
