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
  import Stepper from "../components/Stepper.svelte";
  import { beginGithubOauth, GH_ORG } from "../lib/config.js";

  let { prefs } = $props();

  const alreadyLinked = $derived(Boolean(prefs?.github?.login));
</script>

<div class="stack">
  <Stepper completed={alreadyLinked ? 2 : 1} />

  <section class="card hero">
    <div class="hero-icon"><Icon name="github" size={30} /></div>
    <h1>Authenticate on GitHub</h1>
    <p class="prose">
      Verifying your GitHub identity lets Boxer connect your Apache account to
      your GitHub account. We need this to know who you are on GitHub, to invite
      you to the <span class="mono">{GH_ORG}</span> organisation if you are not
      a member yet, and to vouch for your identity when a project uses Trusted
      Publishing.
    </p>

    {#if alreadyLinked}
      <p class="linked">
        <Icon name="check" size={16} />
        Currently linked to
        <a
          class="mono"
          href={`https://github.com/${prefs.github.login}`}
          target="_blank"
          rel="noopener noreferrer">{prefs.github.login}</a
        >. Re-authenticating refreshes the link.
      </p>
    {/if}

    <button class="btn btn-primary btn-lg" type="button" onclick={beginGithubOauth}>
      <Icon name="github" size={18} />
      {alreadyLinked ? "Re-verify with GitHub" : "Authenticate with GitHub"}
    </button>
    <p class="small faint">
      You will be sent to github.com and returned here afterwards. Boxer only
      asks for your public profile.
    </p>
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
    background: var(--surface-2);
    color: var(--text);
  }

  .hero .prose {
    margin: 0 auto 22px;
    color: var(--text-muted);
    text-align: left;
  }

  .linked {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 14px;
    margin-bottom: 20px;
    border-radius: 999px;
    background: var(--success-soft);
    color: var(--success);
    font-size: 0.88rem;
  }

  .hero .small {
    margin: 14px 0 0;
  }
</style>
