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
  import Icon from "./Icon.svelte";
  import { githubUrl, gitboxUrl } from "../lib/config.js";

  /** @property {{repositories: string[], private: string[], metadata: object}} github */
  let { github } = $props();

  let filter = $state("");
  let showArchived = $state(false);

  const all = $derived(
    [...(github.repositories ?? [])].sort((a, b) => a.localeCompare(b)).map((name) => {
      const meta = github.metadata?.[name] ?? {};
      return {
        name,
        archived: Boolean(meta.archived),
        description: meta.description || "",
        isPrivate: (github.private ?? []).includes(name),
      };
    }),
  );

  const archivedCount = $derived(all.filter((r) => r.archived).length);

  const visible = $derived(
    all.filter((repo) => {
      if (repo.archived && !showArchived) return false;
      const q = filter.trim().toLowerCase();
      if (!q) return true;
      return (
        repo.name.toLowerCase().includes(q) ||
        repo.description.toLowerCase().includes(q)
      );
    }),
  );
</script>

<section class="card">
  <div class="card-head">
    <div>
      <h2>Repository write access</h2>
      <p class="sub">
        {all.length}
        {all.length === 1 ? "repository" : "repositories"} you can push to
        {#if archivedCount}· {archivedCount} archived{/if}
      </p>
    </div>
    <div class="controls">
      {#if archivedCount}
        <label class="checkbox small">
          <input type="checkbox" bind:checked={showArchived} />
          Show archived
        </label>
      {/if}
      <label class="search">
        <Icon name="search" size={15} />
        <input
          type="search"
          placeholder="Filter repositories"
          bind:value={filter}
          aria-label="Filter repositories"
        />
      </label>
    </div>
  </div>

  {#if visible.length === 0}
    <div class="card-body empty">
      <Icon name="search" size={22} />
      <p>No repositories match “{filter}”.</p>
    </div>
  {:else}
    <div class="scroller">
      <table class="data">
        <thead>
          <tr>
            <th scope="col">Repository</th>
            <th scope="col">Visibility</th>
            <th scope="col" class="desc-col">Description</th>
            <th scope="col" class="right">Links</th>
          </tr>
        </thead>
        <tbody>
          {#each visible as repo (repo.name)}
            <tr class:archived={repo.archived}>
              <td>
                <span class="repo-name mono">{repo.name}.git</span>
                {#if repo.archived}
                  <span class="badge">archived</span>
                {/if}
              </td>
              <td>
                {#if repo.isPrivate}
                  <span class="badge badge-danger">
                    <Icon name="eye-off" size={12} /> Private
                  </span>
                {:else}
                  <span class="badge badge-success">
                    <Icon name="globe" size={12} /> Public
                  </span>
                {/if}
              </td>
              <td class="desc" title={repo.description}>{repo.description}</td>
              <td class="right nowrap">
                <a
                  class="repo-link"
                  href={githubUrl(repo.name)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="github" size={14} /> GitHub
                </a>
                <a
                  class="repo-link"
                  href={gitboxUrl(repo.name, repo.isPrivate)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon name="branch" size={14} /> GitBox
                </a>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .controls {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }

  .search {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 10px;
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text-faint);
  }

  .search:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent);
  }

  .search input {
    width: 210px;
    padding: 7px 0;
    border: 0;
    background: none;
    color: var(--text);
  }

  .search input:focus {
    outline: none;
    box-shadow: none;
  }

  .scroller {
    max-height: 620px;
    overflow: auto;
    border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  }

  .repo-name {
    font-size: 0.88rem;
    font-weight: 550;
  }

  tr.archived .repo-name {
    color: var(--text-faint);
    text-decoration: line-through;
  }

  .desc {
    max-width: 520px;
    overflow: hidden;
    color: var(--text-muted);
    font-size: 0.85rem;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .right {
    text-align: right;
  }

  .nowrap {
    white-space: nowrap;
  }

  .repo-link {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-left: 14px;
    color: var(--text-muted);
    font-size: 0.82rem;
    font-weight: 550;
  }

  .repo-link:hover {
    color: var(--accent-text);
    text-decoration: none;
  }

  .empty {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    color: var(--text-muted);
  }

  .empty p {
    margin: 0;
  }

  @media (max-width: 760px) {
    .desc,
    .desc-col {
      display: none;
    }

    .repo-link {
      margin-left: 10px;
    }

    .search input {
      width: 140px;
    }
  }
</style>
