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
  import { href, link, route } from "../lib/router.js";
  import { INFRA_CONTACT } from "../lib/config.js";

  let { prefs = null, onLogout } = $props();

  const isAdmin = $derived(Boolean(prefs?.credentials?.admin));
  const currentAction = $derived($route.action || "preferences");

  /** Nav model. `admin: true` entries are hidden from non-admins. */
  const menus = $derived([
    {
      id: "you",
      label: "You",
      items: [
        {
          action: "preferences",
          icon: "user",
          label: "Your account",
          desc: "Your link status and the repositories you can write to.",
        },
        {
          action: "verify",
          icon: "shield",
          label: "Verify your GitHub identity",
          desc: "Required for Trusted Publishing.",
        },
        {
          icon: "logout",
          label: "Log out",
          desc: "End your session and clear your cookie.",
          onSelect: onLogout,
        },
      ],
    },
    {
      id: "repos",
      label: "Repositories",
      items: [
        {
          action: "newrepo",
          icon: "repo-plus",
          label: "Create a repository",
          desc: "Set up a new repository on GitHub and GitBox.",
        },
        {
          action: "defaultbranch",
          icon: "branch",
          label: "Change default branch",
          desc: "Point a repository at a different default branch.",
        },
        {
          action: "search",
          icon: "search",
          label: "User search",
          desc: "Look up a user's GitBox/GitHub access level.",
          admin: true,
        },
      ],
    },
    {
      id: "help",
      label: "Help",
      items: [
        {
          action: "faq",
          icon: "book",
          label: "Frequently asked questions",
          desc: "Answers to the questions we get most often.",
        },
        {
          url: INFRA_CONTACT,
          icon: "mail",
          label: "Contact Infrastructure",
          desc: "Ask us anything Boxer could not answer.",
        },
      ],
    },
  ]);

  const visibleMenus = $derived(
    menus.map((menu) => ({
      ...menu,
      items: menu.items.filter((item) => !item.admin || isAdmin),
    })),
  );

  let openMenu = $state(null);
  let mobileOpen = $state(false);
  /** The whole bar, including the hamburger, counts as "inside" the menu. */
  let barEl;

  function toggle(id) {
    openMenu = openMenu === id ? null : id;
  }

  function closeAll() {
    openMenu = null;
    mobileOpen = false;
  }

  function onWindowClick(event) {
    if (barEl && !barEl.contains(event.target)) closeAll();
  }

  function onWindowKeydown(event) {
    if (event.key === "Escape") closeAll();
  }

  function select(item, event) {
    if (item.onSelect) {
      event.preventDefault();
      item.onSelect();
    }
    closeAll();
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onWindowKeydown} />

<header class="appbar">
  <div class="appbar-inner" bind:this={barEl}>
    <a class="brand" href={href("")} use:link onclick={closeAll}>
      <img src="./images/logo.png" alt="" width="34" height="34" />
      <span class="brand-text">
        <strong>Boxer</strong>
        <em>ASF Infrastructure</em>
      </span>
    </a>

    <button
      class="hamburger"
      type="button"
      aria-expanded={mobileOpen}
      aria-controls="primary-nav"
      onclick={() => (mobileOpen = !mobileOpen)}
    >
      <Icon name={mobileOpen ? "close" : "menu"} size={20} />
      <span class="sr-only">Menu</span>
    </button>

    <nav
      id="primary-nav"
      class="nav"
      class:open={mobileOpen}
      aria-label="Primary"
    >
      <a class="nav-link" href="https://gitbox.apache.org/" onclick={closeAll}>
        <Icon name="home" size={16} />
        GitBox
      </a>

      {#each visibleMenus as menu (menu.id)}
        <div class="menu" class:open={openMenu === menu.id}>
          <button
            class="nav-link"
            class:active={menu.items.some((i) => i.action === currentAction)}
            type="button"
            aria-expanded={openMenu === menu.id}
            onclick={() => toggle(menu.id)}
          >
            {menu.label}
            <span class="caret" class:flip={openMenu === menu.id}>
              <Icon name="chevron-down" size={15} />
            </span>
          </button>

          {#if openMenu === menu.id}
            <div class="dropdown">
              {#each menu.items as item (item.label)}
                <a
                  class="dropdown-item"
                  class:active={item.action && item.action === currentAction}
                  href={item.url ?? href(item.action ?? "")}
                  target={item.url ? "_blank" : undefined}
                  rel={item.url ? "noopener noreferrer" : undefined}
                  use:link
                  onclick={(e) => select(item, e)}
                >
                  <span class="dropdown-icon"><Icon name={item.icon} size={18} /></span>
                  <span class="dropdown-copy">
                    <span class="dropdown-title">
                      {item.label}
                      {#if item.url}<Icon name="external" size={12} />{/if}
                    </span>
                    <span class="dropdown-desc">{item.desc}</span>
                  </span>
                </a>
              {/each}
            </div>
          {/if}
        </div>
      {/each}

      {#if prefs?.credentials?.uid}
        <span class="whoami" title={prefs.credentials.fullname || ""}>
          {#if prefs.github?.login}
            <img
              class="whoami-avatar"
              src={`https://github.com/${prefs.github.login}.png?size=48`}
              alt=""
              width="24"
              height="24"
              loading="lazy"
            />
          {:else}
            <Icon name="user" size={15} />
          {/if}
          {prefs.credentials.uid}
          {#if isAdmin}<span class="admin-chip">admin</span>{/if}
        </span>
      {/if}
    </nav>
  </div>
</header>

<style>
  .appbar {
    position: sticky;
    top: 0;
    z-index: 40;
    background: var(--shell);
    border-bottom: 1px solid rgb(255 255 255 / 8%);
  }

  .appbar-inner {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    max-width: var(--content-width);
    min-height: var(--header-height);
    margin: 0 auto;
    padding: 0 24px;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-right: 18px;
    color: var(--text-on-shell);
    text-decoration: none;
  }

  .brand:hover {
    text-decoration: none;
  }

  .brand img {
    border-radius: 7px;
    background: rgb(255 255 255 / 6%);
    padding: 2px;
  }

  .brand-text {
    display: flex;
    flex-direction: column;
    line-height: 1.15;
  }

  .brand-text strong {
    font-size: 1.02rem;
    font-weight: 650;
    letter-spacing: -0.01em;
  }

  .brand-text em {
    font-size: 0.71rem;
    font-style: normal;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--text-on-shell-muted);
  }

  .nav {
    display: flex;
    align-items: center;
    gap: 2px;
    flex: 1;
  }

  .nav-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--text-on-shell-muted);
    font: inherit;
    font-size: 0.9rem;
    font-weight: 520;
    cursor: pointer;
    white-space: nowrap;
    transition: background-color 0.14s ease, color 0.14s ease;
  }

  .nav-link:hover,
  .nav-link[aria-expanded="true"] {
    background: rgb(255 255 255 / 8%);
    color: var(--text-on-shell);
    text-decoration: none;
  }

  .nav-link.active {
    color: var(--text-on-shell);
  }

  .caret {
    display: flex;
    transition: transform 0.16s ease;
  }

  .caret.flip {
    transform: rotate(180deg);
  }

  .menu {
    position: relative;
  }

  .dropdown {
    position: absolute;
    top: calc(100% + 8px);
    left: 0;
    z-index: 50;
    width: 330px;
    padding: 6px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    box-shadow: var(--shadow-lg);
    animation: drop 0.13s ease-out;
  }

  @keyframes drop {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
  }

  .dropdown-item {
    display: flex;
    gap: 12px;
    padding: 10px;
    border-radius: var(--radius-sm);
    color: var(--text);
    text-decoration: none;
  }

  .dropdown-item:hover,
  .dropdown-item.active {
    background: var(--surface-2);
    text-decoration: none;
  }

  .dropdown-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    flex: none;
    border-radius: 8px;
    background: var(--accent-soft);
    color: var(--accent-text);
  }

  .dropdown-copy {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }

  .dropdown-title {
    display: flex;
    align-items: center;
    gap: 5px;
    font-weight: 570;
    font-size: 0.9rem;
  }

  .dropdown-desc {
    font-size: 0.8rem;
    line-height: 1.4;
    color: var(--text-muted);
  }

  .whoami {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    margin-left: auto;
    padding: 5px 10px 5px 6px;
    border-radius: 999px;
    background: rgb(255 255 255 / 7%);
    color: var(--text-on-shell);
    font-size: 0.83rem;
    font-weight: 550;
  }

  .whoami-avatar {
    border-radius: 50%;
  }

  .admin-chip {
    padding: 1px 7px;
    border-radius: 999px;
    background: var(--accent);
    color: #fff;
    font-size: 0.66rem;
    font-weight: 650;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .hamburger {
    display: none;
    align-items: center;
    justify-content: center;
    margin-left: auto;
    padding: 8px;
    border: 0;
    border-radius: var(--radius-sm);
    background: rgb(255 255 255 / 8%);
    color: var(--text-on-shell);
    cursor: pointer;
  }

  @media (max-width: 860px) {
    .appbar-inner {
      flex-wrap: wrap;
      padding: 0 16px;
    }

    .hamburger {
      display: inline-flex;
    }

    .nav {
      display: none;
      flex-basis: 100%;
      flex-direction: column;
      align-items: stretch;
      gap: 2px;
      padding: 8px 0 14px;
    }

    .nav.open {
      display: flex;
    }

    .nav-link {
      width: 100%;
      padding: 11px 12px;
      font-size: 0.95rem;
    }

    /* Only the section toggles push their caret to the far edge. */
    button.nav-link {
      justify-content: space-between;
    }

    .dropdown {
      position: static;
      width: auto;
      margin: 2px 0 6px;
      box-shadow: none;
      animation: none;
    }

    .whoami {
      margin: 8px 0 0;
      align-self: flex-start;
    }
  }
</style>
