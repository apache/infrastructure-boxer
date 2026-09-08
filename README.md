# infrastructure-boxer
The ASF Infrastructure Boxer Application provides services for ASF committers and Members who are working with Git repositories. Its current services are:

- a [list of Apache GitHub repositories](https://gitbox.apache.org/repos/asf), original or mirrored, with links to their logs.
- [Boxer](https://gitbox.apache.org/boxer/), a tool providing
  - account management: associate a user's Git account with their ASF account.
  - repository management: easily create a new Git repository within the ASF system, and sync repositories and teams to GitHub

## Repository layout

- `server/` — the aiohttp backend that serves the `api/` endpoints.
- `webui/` — the Svelte + Vite front-end. Source in `webui/src`, built site in
  `webui/dist`; see [webui/README.md](webui/README.md) for how to build and
  deploy it.
- `htdocs/` — the previous hand-written front-end, kept until the deployment is
  pointed at `webui/dist`.
