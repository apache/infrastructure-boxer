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
  import { href, link } from "../lib/router.js";
  import { INFRA_CONTACT, INFRA_MAIL } from "../lib/config.js";

  const year = new Date().getFullYear();
</script>

<footer class="appfoot">
  <div class="appfoot-inner">
    <div class="colophon">
      <img src="./images/asf.png" alt="" width="20" height="30" />
      <p>
        Boxer is run by <a href="https://infra.apache.org/">ASF Infrastructure</a>.
        Copyright © {year} The Apache Software Foundation, licensed under the
        <a href="https://www.apache.org/licenses/LICENSE-2.0">Apache License 2.0</a>.
      </p>
    </div>
    <nav class="links" aria-label="Footer">
      <a href={href("faq")} use:link>FAQ</a>
      <a href={INFRA_CONTACT}>Contact</a>
      <a href={`mailto:${INFRA_MAIL}`}>{INFRA_MAIL}</a>
      <a href="https://gitbox.apache.org/repos/asf">Repository list</a>
    </nav>
  </div>
</footer>

<style>
  .appfoot {
    flex: none;
    margin-top: auto;
    background: var(--shell);
    color: var(--text-on-shell-muted);
    font-size: 0.85rem;
  }

  .appfoot-inner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    flex-wrap: wrap;
    max-width: var(--content-width);
    margin: 0 auto;
    padding: 22px 24px;
  }

  .colophon {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    max-width: 62ch;
  }

  .colophon p {
    margin: 0;
    line-height: 1.5;
  }

  .links {
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
  }

  .appfoot a {
    color: var(--text-on-shell);
  }
</style>
