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

  /**
   * Onboarding progress. Replaces the old v_stepN.png images with real markup
   * so it scales, reflows on small screens and reads correctly to a screen
   * reader.
   *
   * @property {number} completed - how many of the five steps are done.
   */
  let { completed = 0 } = $props();

  const steps = [
    { icon: "asf", label: "Authenticated with ASF" },
    { icon: "github", label: "Authenticated with GitHub" },
    { icon: "users", label: "Member of GitHub org" },
    { icon: "lock", label: "MFA verified" },
    { icon: "link", label: "Accounts linked" },
  ];
</script>

<ol class="stepper" aria-label={`Setup progress: ${completed} of ${steps.length} steps complete`}>
  {#each steps as step, i (step.label)}
    {@const done = i < completed}
    {@const current = i === completed}
    <li class="step" class:done class:current>
      <span class="rail" aria-hidden="true"></span>
      <span class="dot" class:brand={step.icon === "asf"}>
        {#if step.icon === "asf"}
          <img src="./images/asf.png" alt="" width="16" height="24" />
        {:else}
          <Icon name={step.icon} size={19} />
        {/if}
        {#if done}
          <span class="tick"><Icon name="check" size={11} stroke={3.5} /></span>
        {/if}
      </span>
      <span class="label">{step.label}</span>
      <span class="sr-only">{done ? "— complete" : current ? "— in progress" : "— pending"}</span>
    </li>
  {/each}
</ol>

<style>
  .stepper {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 0;
    margin: 0 0 28px;
    padding: 4px 0 0;
    list-style: none;
  }

  .step {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 0 4px;
    text-align: center;
  }

  /* Connecting rail, drawn behind the dots. */
  .rail {
    position: absolute;
    top: 19px;
    left: -50%;
    width: 100%;
    height: 3px;
    border-radius: 2px;
    background: var(--surface-3);
  }

  .step:first-child .rail {
    display: none;
  }

  .step.done .rail,
  .step.current .rail {
    background: var(--accent);
  }

  .dot {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: 2px solid var(--border-strong);
    border-radius: 50%;
    background: var(--surface);
    color: var(--text-faint);
  }

  .step.done .dot {
    border-color: var(--accent);
    background: var(--accent);
    color: #fff;
  }

  .step.current .dot {
    border-color: var(--accent);
    color: var(--accent-text);
    box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 18%, transparent);
  }

  /* The ASF feather is a brand mark, so it keeps its own colours and sits on
     a plain surface rather than being flattened into the accent fill. */
  .step.done .dot.brand {
    background: var(--surface);
    border-color: var(--accent);
  }

  .dot img {
    opacity: 0.9;
  }

  .step.done .dot img,
  .step.current .dot img {
    opacity: 1;
  }

  .tick {
    position: absolute;
    right: -3px;
    bottom: -3px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border: 2px solid var(--surface);
    border-radius: 50%;
    background: var(--success);
    color: #fff;
  }

  .label {
    max-width: 14ch;
    font-size: 0.78rem;
    line-height: 1.3;
    color: var(--text-muted);
  }

  .step.done .label,
  .step.current .label {
    color: var(--text);
    font-weight: 550;
  }

  @media (max-width: 700px) {
    .stepper {
      grid-auto-flow: row;
      grid-auto-columns: auto;
      gap: 2px;
      justify-items: start;
    }

    .step {
      flex-direction: row;
      align-items: center;
      gap: 12px;
      padding: 3px 0;
      text-align: left;
    }

    .rail {
      top: -8px;
      left: 19px;
      width: 3px;
      height: 16px;
    }

    .label {
      max-width: none;
      font-size: 0.88rem;
    }
  }
</style>
