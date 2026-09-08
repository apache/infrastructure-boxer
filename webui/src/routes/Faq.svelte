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
  import { INFRA_MAIL } from "../lib/config.js";

  const faqs = [
    {
      q: "If I change my LDAP password, do I have to re-authenticate with GitBox?",
      a: "No. Changing your Apache password does not affect your GitBox or GitHub link.",
    },
    {
      q: "If I unlink my GitHub account, can I still commit through GitBox?",
      a:
        "Yes. GitBox is meant for people who want to commit to git without having to " +
        "worry about GitHub — some users have concerns about GitHub's terms of service. " +
        "Nothing at the ASF requires you to use GitHub. Projects may track issues and " +
        "pull requests there, but you can commit solely through GitBox if you prefer.",
    },
    {
      q: "How do I add or remove a repository from the list I can write to?",
      a:
        "Repository access is managed automatically from your ASF project membership. " +
        "New repositories in a project you belong to appear in your list within a few " +
        "minutes of being created. You cannot be removed from a single repository — " +
        "leaving a project removes you from all of that project's repositories.",
    },
    {
      q: "Why does Boxer insist on multi-factor authentication?",
      a:
        "The Apache organisation on GitHub requires MFA for every member with write " +
        "access. Boxer cannot grant you repository access until GitHub reports that " +
        "MFA is enabled on your account, which can take up to five minutes after you " +
        "turn it on.",
    },
    {
      q: "Who can see which project teams I am listed in?",
      a:
        "Only members of the Apache GitHub organisation can see team membership, and " +
        "only for the teams you explicitly opt into on your account page. Team listing " +
        "is off by default, and you can opt out again at any time.",
    },
  ];
</script>

<div class="page-head">
  <h1>Frequently asked questions</h1>
  <p class="lede">
    Answers to the questions ASF Infrastructure gets asked most often about
    Boxer, GitBox and GitHub.
  </p>
</div>

<div class="faq">
  {#each faqs as item, i (item.q)}
    <details class="card" open={i === 0}>
      <summary>
        <span>{item.q}</span>
        <span class="chev"><Icon name="chevron-down" size={17} /></span>
      </summary>
      <div class="answer">{item.a}</div>
    </details>
  {/each}
</div>

<section class="card ask">
  <div class="card-body">
    <h2>Still stuck?</h2>
    <p class="muted">
      Ask on <a href={`mailto:${INFRA_MAIL}`}>{INFRA_MAIL}</a> and we will answer
      — and add the question here if others are likely to hit it too.
    </p>
  </div>
</section>

<style>
  .faq {
    display: grid;
    gap: 10px;
    max-width: 820px;
  }

  details {
    overflow: hidden;
  }

  summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 15px 20px;
    cursor: pointer;
    font-weight: 570;
    list-style: none;
  }

  summary::-webkit-details-marker {
    display: none;
  }

  summary:hover {
    background: var(--surface-2);
  }

  .chev {
    color: var(--text-faint);
    transition: transform 0.16s ease;
  }

  details[open] .chev {
    transform: rotate(180deg);
  }

  .answer {
    padding: 0 20px 18px;
    color: var(--text-muted);
    line-height: 1.6;
  }

  .ask {
    max-width: 820px;
    margin-top: 20px;
  }

  .ask h2 {
    font-size: 1.05rem;
  }

  .ask p {
    margin: 0;
  }
</style>
