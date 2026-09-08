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
</script>

<div class="stack">
  <Stepper completed={3} />

  <section class="card hero">
    <div class="hero-icon"><Icon name="lock" size={28} /></div>
    <h1>Enable multi-factor authentication</h1>
    <p class="prose">
      You have not enabled multi-factor authentication (MFA) on GitHub yet. We
      cannot grant write access to Apache repositories to accounts without MFA,
      so this is the last step before you are done.
    </p>

    <a
      class="btn btn-primary btn-lg"
      href="https://github.com/settings/security"
      target="_blank"
      rel="noopener noreferrer"
    >
      <Icon name="external" size={16} /> Open GitHub account security
    </a>

    <ol class="steps prose">
      <li>Turn on two-factor authentication in your GitHub security settings.</li>
      <li>Come back here and reload this page.</li>
      <li>
        If you already enabled it, give Boxer up to five minutes to pick up the
        change.
      </li>
    </ol>

    <button class="btn" type="button" onclick={() => location.reload()}>
      Reload and re-check
    </button>
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
    background: var(--warn-soft);
    color: var(--warn);
  }

  .hero .prose {
    margin: 0 auto 22px;
    color: var(--text-muted);
    text-align: left;
  }

  .steps {
    margin: 26px auto;
    padding-left: 22px;
    color: var(--text-muted);
    font-size: 0.9rem;
    text-align: left;
  }

  .steps li + li {
    margin-top: 5px;
  }
</style>
