# Boxer web UI

The front-end for the ASF Infrastructure Boxer service, built with
[Svelte 5](https://svelte.dev/) and [Vite](https://vite.dev/).

It replaces the hand-rolled `document.createElement` DOM building in
`htdocs/js/boxer.js` with components, and the single `boxer.scss` stylesheet
with a small design-token system that supports light and dark colour schemes.

## Layout

```
webui/
├── index.html          # Vite entry document
├── public/             # copied verbatim into dist/
│   ├── images/         # logo.png, asf.png
│   └── faq.html        # redirect for the old /boxer/faq.html URL
├── src/
│   ├── main.js         # mounts <App/>
│   ├── app.css         # design tokens, reset, shared component classes
│   ├── App.svelte      # boot sequence (the old prime()) and page switch
│   ├── lib/
│   │   ├── api.js      # fetch wrappers + one function per API endpoint
│   │   ├── config.js   # org, OAuth client id, URL builders
│   │   ├── dialogs.js  # promise-based confirm()/alert() replacements
│   │   └── router.js   # ?action=… query-string router
│   ├── components/     # header, footer, stepper, icons, dialogs, repo table
│   └── routes/         # one component per page
└── dist/               # build output (committed; see .gitignore)
```

## Development

```sh
npm install
npm run dev      # http://localhost:5173, proxies /api to 127.0.0.1:8080
npm run build    # writes dist/
npm run preview  # serve dist/ locally
```

`npm run dev` proxies `/api/*` to a Boxer server running on port 8080 (see
`server/boxer.yaml`), so the dev server talks to a real backend.

## Deployment

`npm run build` produces a fully static `dist/` with relative asset URLs, so it
can be served from any sub-path. Point the web server at `webui/dist` where it
currently points at `htdocs`, keeping the API mounted at `api/` next to it —
for example `https://gitbox.apache.org/boxer/` serving `dist/` and
`https://gitbox.apache.org/boxer/api/…` proxied to the Boxer server.

## URLs

The `?action=…` URLs the old app used are unchanged, because the OAuth
providers redirect back to `?action=oauth` and people have the others
bookmarked:

| URL                    | Page                                              |
| ---------------------- | ------------------------------------------------- |
| `/`, `?action=preferences` | Your account (or the onboarding step you are on) |
| `?action=verify`       | Re-verify your GitHub identity                    |
| `?action=newrepo`      | Create a repository                               |
| `?action=defaultbranch`| Change a repository's default branch              |
| `?action=search`       | User search (administrators only)                 |
| `?action=faq`          | FAQ (`faq.html` redirects here)                   |
| `?action=oauth`        | OAuth callback, handled during boot               |

Navigation between them happens client-side; there is no full page load.
