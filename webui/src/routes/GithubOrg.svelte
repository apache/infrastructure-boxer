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
  import Stepper from "../components/Stepper.svelte";
  import { api } from "../lib/api.js";
  import { GH_ORG } from "../lib/config.js";

  /** How often we re-check whether the invitation has been accepted. */
  const POLL_INTERVAL = 10_000;

  /** "idle" -> "sending" -> "waiting" | "error" | "reauth" | "accepted" */
  let phase = $state("idle");
  let errorMessage = $state("");
  let pollTimer = null;

  async function sendInvite() {
    phase = "sending";
    errorMessage = "";
    let rv;
    try {
      rv = await api.invite();
    } catch (e) {
      phase = "error";
      errorMessage = e.message;
      return;
    }
    if (rv.okay) {
      phase = "waiting";
      pollTimer = window.setTimeout(pollMembership, POLL_INTERVAL);
    } else if (rv.reauth === true) {
      // The user was in the org before and left; GitHub needs a fresh OAuth.
      phase = "reauth";
      window.setTimeout(() => {
        location.search = "";
        location.reload();
      }, 3000);
    } else {
      phase = "error";
      errorMessage =
        rv.message || "Something went wrong — you may already have a pending invitation.";
    }
  }

  async function pollMembership() {
    try {
      const prefs = await api.preferences();
      if (prefs?.credentials?.github_org_member) {
        phase = "accepted";
        window.setTimeout(() => {
          location.search = "";
          location.reload();
        }, 3000);
        return;
      }
    } catch {
      // A hiccup while polling is not fatal; try again on the next tick.
    }
    pollTimer = window.setTimeout(pollMembership, POLL_INTERVAL);
  }

  $effect(() => () => window.clearTimeout(pollTimer));
</script>

<div class="stack">
  <Stepper completed={phase === "accepted" ? 3 : 2} />

  <section class="card hero">
    <div class="hero-icon"><Icon name="users" size={28} /></div>
    <h1>Join the {GH_ORG} organisation on GitHub</h1>

    {#if phase === "accepted"}
      <Notice tone="success" title="Invitation accepted">
        <p>Your organisation membership was recorded. Reloading Boxer…</p>
      </Notice>
    {:else if phase === "reauth"}
      <Notice tone="warn" title="Re-authentication needed">
        <p>
          It looks like you were a member of the organisation before and then
          left. We need to re-authenticate you on GitHub to fix that — hang on
          while we sort it out…
        </p>
      </Notice>
    {:else if phase === "waiting"}
      <p class="prose">
        An invitation has been sent to your email address. You can also review it
        directly on GitHub.
      </p>
      <a
        class="btn"
        href={`https://github.com/orgs/${GH_ORG}/invitation`}
        target="_blank"
        rel="noopener noreferrer"
      >
        <Icon name="external" size={15} /> Review invitation on GitHub
      </a>
      <div class="waiting">
        <Spinner size={18} />
        <p>
          Once you accept, Boxer starts adding you to the teams you belong to.
          This can take up to five minutes. This page reloads by itself as soon
          as your invitation is recorded — sit tight.
        </p>
      </div>
    {:else}
      <p class="prose">
        You are not part of the Apache organisation on GitHub yet. Organisation
        membership is what grants you write access to Apache repositories on
        GitHub.
      </p>
      {#if phase === "error"}
        <Notice tone="danger" title="Invitation failed">
          <p>{errorMessage}</p>
        </Notice>
      {/if}
      <button
        class="btn btn-primary btn-lg"
        type="button"
        onclick={sendInvite}
        disabled={phase === "sending"}
      >
        {#if phase === "sending"}<Spinner size={15} />{/if}
        {phase === "sending" ? "Sending invitation…" : "Send my invitation"}
      </button>
    {/if}
  </section>
</div>

<style>
  .hero {
    max-width: 720px;
    margin: 0 auto;
    padding: 36px 32px 32px;
    text-align: center;
  }

  .hero-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 62px;
    height: 62px;
    margin-bottom: 18px;
    border-radius: 50%;
    background: var(--accent-soft);
    color: var(--accent-text);
  }

  .hero .prose {
    margin: 0 auto 22px;
    color: var(--text-muted);
    text-align: left;
  }

  .waiting {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    max-width: 60ch;
    margin: 26px auto 0;
    padding: 16px;
    border-radius: var(--radius);
    background: var(--surface-2);
    text-align: left;
  }

  .waiting p {
    margin: 0;
    color: var(--text-muted);
    font-size: 0.88rem;
  }
</style>
