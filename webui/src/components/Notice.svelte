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

  /** @property {"info"|"success"|"warn"|"danger"} tone */
  let { tone = "info", title = null, children = undefined } = $props();

  const icons = {
    info: "info",
    success: "check",
    warn: "alert",
    danger: "alert",
  };
</script>

<div class={`notice ${tone}`} role={tone === "danger" ? "alert" : "status"}>
  <span class="notice-icon"><Icon name={icons[tone]} size={17} /></span>
  <div class="notice-body">
    {#if title}<strong>{title}</strong>{/if}
    {@render children?.()}
  </div>
</div>

<style>
  .notice {
    display: flex;
    gap: 11px;
    padding: 12px 14px;
    border: 1px solid transparent;
    border-radius: var(--radius);
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .notice-body {
    min-width: 0;
  }

  .notice-body strong {
    display: block;
    margin-bottom: 2px;
    font-weight: 600;
  }

  .notice-icon {
    padding-top: 1px;
  }

  .info {
    border-color: color-mix(in srgb, var(--accent) 30%, transparent);
    background: var(--accent-soft);
    color: var(--accent-text);
  }

  .success {
    border-color: color-mix(in srgb, var(--success) 32%, transparent);
    background: var(--success-soft);
    color: var(--success);
  }

  .warn {
    border-color: color-mix(in srgb, var(--warn) 32%, transparent);
    background: var(--warn-soft);
    color: var(--warn);
  }

  .danger {
    border-color: color-mix(in srgb, var(--danger) 32%, transparent);
    background: var(--danger-soft);
    color: var(--danger);
  }
</style>
