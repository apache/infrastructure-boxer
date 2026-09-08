/*
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing,
software distributed under the License is distributed on an
"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
KIND, either express or implied.  See the License for the
specific language governing permissions and limitations
under the License.
*/

// Query-string router.
//
// Boxer has always addressed its pages as `?action=<name>`, and both OAuth
// providers redirect back to `?action=oauth`, so those URLs are part of the
// service's contract. This keeps them, while giving the SPA client-side
// navigation and working back/forward buttons.

import { readable } from "svelte/store";

/** Parse `location.search` into a plain object. */
export function queryParams(search = location.search) {
  return Object.fromEntries(new URLSearchParams(search).entries());
}

function currentRoute() {
  const params = queryParams();
  return { action: params.action || "", params };
}

/** Current route, updated on navigation. */
export const route = readable(currentRoute(), (set) => {
  const update = () => set(currentRoute());
  window.addEventListener("popstate", update);
  window.addEventListener("boxer:navigate", update);
  return () => {
    window.removeEventListener("popstate", update);
    window.removeEventListener("boxer:navigate", update);
  };
});

/** Build an in-app href, e.g. `href("search", {query: "humbedooh"})`. */
export function href(action, params = {}) {
  const qs = new URLSearchParams(action ? { action, ...params } : params);
  const s = qs.toString();
  return s ? `?${s}` : location.pathname;
}

/** Navigate without a page load. */
export function navigate(action, params = {}, { replace = false } = {}) {
  const url = href(action, params);
  history[replace ? "replaceState" : "pushState"]({}, "", url);
  window.dispatchEvent(new Event("boxer:navigate"));
}

/**
 * Update the query string of the current page without adding history entries
 * (used by the search box so results stay linkable).
 */
export function replaceQuery(action, params = {}) {
  navigate(action, params, { replace: true });
}

/**
 * Intercept clicks on same-page `?action=` links so they route client-side.
 * Modifier-clicks and external links keep their normal behaviour.
 */
export function link(node) {
  const onClick = (event) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    const anchor = event.currentTarget;
    if (anchor.target && anchor.target !== "_self") return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname) {
      return;
    }
    event.preventDefault();
    if (url.search === location.search) return;
    history.pushState({}, "", url.search || url.pathname);
    window.dispatchEvent(new Event("boxer:navigate"));
  };
  node.addEventListener("click", onClick);
  return { destroy: () => node.removeEventListener("click", onClick) };
}
