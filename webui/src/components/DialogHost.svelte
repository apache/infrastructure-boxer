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
  import { activeDialog, closeDialog } from "../lib/dialogs.js";

  let confirmButton = $state(null);

  // Move focus into the dialog as soon as it appears.
  $effect(() => {
    if ($activeDialog && confirmButton) confirmButton.focus();
  });

  function onKeydown(event) {
    if (!$activeDialog) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDialog(false);
    }
  }
</script>

<svelte:window onkeydown={onKeydown} />

{#if $activeDialog}
  <div
    class="backdrop"
    role="presentation"
    onclick={(e) => e.target === e.currentTarget && closeDialog(false)}
  >
    <div
      class="dialog"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby="dialog-body"
    >
      <h2 id="dialog-title">{$activeDialog.title}</h2>
      <p id="dialog-body">{$activeDialog.body}</p>
      <div class="actions">
        {#if $activeDialog.kind === "confirm"}
          <button class="btn" type="button" onclick={() => closeDialog(false)}>
            {$activeDialog.cancelLabel}
          </button>
        {/if}
        <button
          class="btn btn-primary"
          class:danger={$activeDialog.danger}
          type="button"
          bind:this={confirmButton}
          onclick={() => closeDialog(true)}
        >
          {$activeDialog.confirmLabel}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: rgb(12 15 20 / 55%);
    backdrop-filter: blur(2px);
    animation: fade 0.12s ease-out;
  }

  .dialog {
    width: min(460px, 100%);
    padding: 22px;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    background: var(--surface);
    box-shadow: var(--shadow-lg);
    animation: pop 0.14s ease-out;
  }

  .dialog h2 {
    margin: 0 0 8px;
    font-size: 1.08rem;
  }

  .dialog p {
    margin: 0 0 20px;
    color: var(--text-muted);
    line-height: 1.55;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }

  .btn-primary.danger {
    background: var(--danger);
  }

  .btn-primary.danger:hover {
    background: color-mix(in srgb, var(--danger) 85%, black);
  }

  @keyframes fade {
    from {
      opacity: 0;
    }
  }

  @keyframes pop {
    from {
      opacity: 0;
      transform: translateY(8px) scale(0.98);
    }
  }
</style>
