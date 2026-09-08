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
  let { size = 20, label = null, block = false } = $props();
</script>

<span class="spin-wrap" class:block role="status">
  <span class="spin" style={`--s:${size}px`}></span>
  {#if label}<span class="spin-label">{label}</span>{:else}<span class="sr-only">Loading</span>{/if}
</span>

<style>
  .spin-wrap {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: var(--text-muted);
    font-size: 0.9rem;
  }

  .spin-wrap.block {
    justify-content: center;
    width: 100%;
    padding: 48px 0;
  }

  .spin {
    width: var(--s);
    height: var(--s);
    flex: none;
    border: 2px solid color-mix(in srgb, var(--accent) 25%, transparent);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
