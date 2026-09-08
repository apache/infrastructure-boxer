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

// Promise-based replacements for window.confirm()/window.alert(), rendered by
// <DialogHost/> so the app never hands the browser's own chrome to the user.

import { writable } from "svelte/store";

/** The dialog currently on screen, or null. */
export const activeDialog = writable(null);

function open(dialog) {
  return new Promise((resolve) => {
    activeDialog.set({ ...dialog, resolve });
  });
}

export function closeDialog(result) {
  activeDialog.update((current) => {
    current?.resolve(result);
    return null;
  });
}

/**
 * Ask the user to confirm something. Resolves true when confirmed.
 * @param {{title: string, body: string, confirmLabel?: string,
 *          cancelLabel?: string, danger?: boolean}} options
 */
export function confirm(options) {
  return open({
    kind: "confirm",
    confirmLabel: "Continue",
    cancelLabel: "Cancel",
    danger: false,
    ...options,
  });
}

/** Tell the user something. Resolves when dismissed. */
export function alert(options) {
  return open({
    kind: "alert",
    confirmLabel: "OK",
    danger: false,
    ...options,
  });
}
