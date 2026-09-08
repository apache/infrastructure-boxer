# orgscanner

An auxiliary service for the ASF Infrastructure Boxer suite. It scans one or
more GitHub organizations and writes a YAML snapshot per organization per scan
containing:

- **members**: login, numeric user ID, full name, whether 2FA is enabled, and
  the member's organization role,
- **teams** matching the configured patterns, such as `*-committers` and
  `*-private`: slug, name, numeric ID, privacy, and the member list,
- **repositories**: name/slug, visibility (`public`, `private` or `internal`),
  full URL, whether it is archived, and GitHub's `updatedAt`.

It runs standalone, as a one-shot or a daemon, or inside the Boxer server as an
asynchronous background task.

## Running it standalone

The scanner is a Python 3.11+ package managed with [uv](https://docs.astral.sh/uv/).
It depends only on `aiohttp` and `PyYAML`.

```bash
# from anywhere: inline script metadata, so uv provides the dependencies
uv run orgscanner/scan.py --config /etc/boxer/orgscanner.yaml --once

# or as a module, using orgscanner/pyproject.toml, from the checkout root
uv run --project orgscanner python -m orgscanner --config orgscanner/orgscanner.yaml
```

Without `--once` it keeps scanning on `scan.interval` until it is signalled
with SIGINT or SIGTERM, which is how to run it under systemd.

| Flag | Effect |
| --- | --- |
| `--once` | one scan of every organization, then exit |
| `--org ORG` | restrict to one organization, may be repeated |
| `--full` | ignore the cache and re-read everything |
| `--no-write` | scan without writing snapshots, for a dry run or a cost estimate |
| `--output DIR` | override `output.directory` |
| `-v` / `-q` | debug logging / warnings only |

## Calling it from Boxer

`orgscanner` is a package in the checkout root, so the Boxer server, which runs
out of `server/`, needs the checkout root on `sys.path`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import orgscanner
```

One scan, awaited from a task Boxer already has. This is the simplest
integration and fits straight into `plugins/background.py`:

```python
snapshots = await orgscanner.scan_once("/etc/boxer/orgscanner.yaml")
for org, snapshot in snapshots.items():
    print(org, snapshot.counts())
    mfa = {m.login: m.two_factor_enabled for m in snapshot.members}
```

A long-lived scanner beside the Boxer background loop, which keeps its cache
and its connection pool warm between rounds:

```python
scanner = orgscanner.OrgScanner(orgscanner.load_config("/etc/boxer/orgscanner.yaml"))
asyncio.create_task(scanner.run_forever())   # stops on the stop_event you pass in
...
snapshot = scanner.snapshots.get("apache")   # last successful scan per org
```

Reading the newest snapshot without scanning, for a process that only consumes
the data:

```python
config = orgscanner.load_config("/etc/boxer/orgscanner.yaml")
path = orgscanner.latest_snapshot_path(config.output, "apache")
snapshot = orgscanner.read_snapshot(path)
```

`scan_all()` does not raise when a single organization fails. It logs the
failure, records the reason in `scanner.errors`, and carries on with the rest.

The package ships a `py.typed` marker and is checked with `mypy --strict`, so
callers inside Boxer get full type information. `OrgScanner` accepts anything
satisfying the `QueryClient` protocol in place of the real GraphQL client, which
is what the tests use.

## Configuration

See [orgscanner.yaml](orgscanner.yaml) for the annotated sample. Only the token
and the organizations are required:

```yaml
github:
  token: ghp_...              # or token_file / token_env / $GITHUB_TOKEN
output:
  directory: /var/lib/boxer/orgscanner
  keep_files: 10
scan:
  organizations: [apache]
  team_patterns: ["*-committers", "*-private"]
  interval: 900
```

The token needs `read:org`, and it has to belong to an organization owner, since
GitHub only reports 2FA status to owners. If it does not,
`two_factor_enabled` comes back as null and the scanner logs a warning rather
than quietly reporting everyone as insecure.

Team patterns are `fnmatch` patterns, tested against each team's slug and its
display name, so `*-committers` matches the `httpd-committers` team.

Paths in the configuration file may be relative, in which case they resolve
against the directory holding the configuration file.

## Output

One file per organization per scan, `$org-$timestamp.yaml`, in
`output.directory`:

```
apache-20260908T112624Z.yaml
apache-20260908T114124Z.yaml
apache-latest.yaml -> apache-20260908T114124Z.yaml
```

After each successful scan, all but the newest `output.keep_files` snapshots
for that organization are deleted (10 by default). Rotation only considers
files named `$org-$timestamp.yaml` whose timestamp parses, so the `-latest`
symlink is never rotated, and organization `apache` cannot rotate away the
snapshots of organization `apache-attic`.

Snapshots are written to a temporary file and renamed into place, so a consumer
never reads a half-written file. Each one carries a `scan:` block with the
GraphQL request count, the points spent, retries, the remaining hourly budget
and what was served from cache, which is what to tune `scan.interval` against.

## How it scans

Everything goes through [GraphQL](https://docs.github.com/en/graphql), which is
cheaper and needs fewer round trips than REST for this shape of data. An
organization the size of the ASF's, with 10k+ members, 3k+ repositories and
thousands of teams, will not fit in the 5000 point hourly budget if it is
scanned naively every 15 minutes, so:

**One cheap probe per scan.** A single query returns the organization's database
ID along with its member, team and repository totals. Those totals are the
change signal the cache is keyed on.

**Teams are batched rather than walked.** One round trip per team would mean
thousands of requests. Matching teams are instead requested several per document
using field aliases (`performance.team_batch_size`, 20 by default), with slugs
passed as GraphQL variables rather than interpolated into the document. A team
whose member list spans several pages has its remaining pages queued and
re-batched with whatever else is still outstanding.

**Three sweeps in parallel.** Members, teams and repositories are independent,
and overlapping them hides the per-request latency that dominates a large
organization. `performance.concurrency` bounds the in-flight requests.

**The cache decides what gets re-read.** In short (see [cache.py](cache.py)):

| Data | Re-read when |
| --- | --- |
| Members | the member total changed, or the cached copy is older than `cache.member_ttl` |
| Teams (the list) | the team total changed, or the cached list is older than `cache.team_ttl` |
| A team's members | that team's member count changed, its cached copy aged out, or the team is new |
| Repositories | swept newest-`updatedAt`-first, stopping at the previous sweep's high-water mark, with the rest taken from cache |

Deletions are the one thing this cannot see cheaply, since a deleted repository
or team leaves no trace in an `updatedAt`-ordered sweep. Two things catch them:
a changed total from the probe query invalidates the cache outright, and every
`scan.full_scan_every` rounds (12 by default) the scanner ignores the cache and
re-reads everything. The first scan against an empty cache is always a full one.

In practice a full scan of `apache` costs a few hundred points and an
incremental round costs a handful, which leaves most of the hourly budget for
Boxer's own GitHub traffic on the same token.

**Rate limits and flaky responses** are handled in [ghclient.py](ghclient.py).
Every query asks for GitHub's `rateLimit` block, which is free, so the client
always knows what is left of the budget. It then:

- parks every caller until the budget resets once fewer than
  `performance.rate_limit_reserve` points remain (250 by default, so the scanner
  never starves Boxer itself),
- honours `Retry-After` and `x-ratelimit-reset` on secondary rate limits (HTTP
  403 and 429), falling back to GitHub's documented 60 second wait,
- retries 5xx responses, connection errors and `RATE_LIMITED` errors with
  exponential backoff and jitter,
- treats a GitHub execution timeout, which arrives either as a 502 or as a 200
  carrying "Something went wrong while executing your query", as a reason to
  halve the page size for the rest of that sweep rather than send the same
  doomed query again, growing it back after a run of clean responses. This is
  the failure mode that pinned Boxer's own team loader at 20 results per page;
  here it self-tunes,
- keeps going when a soft error arrives with partial data, such as a suspended
  account inside a connection, logging it instead of discarding the page.

## Tests

```bash
uv run --project orgscanner pytest orgscanner/tests -v
uv run --project orgscanner mypy --config-file orgscanner/pyproject.toml orgscanner
```

The suite drives whole scans against a fake GitHub GraphQL endpoint
(`tests/fakegithub.py`) that honours pagination and alias batching, so the
caching, rotation and retry behaviour is covered without touching the network.
`tests/test_typing.py` pins the public API's inferred types with
`typing.assert_type` and runs mypy over the component, so the type annotations
are covered by the test suite as well as by CI.

## Layout

| File | Purpose |
| --- | --- |
| `scan.py` | standalone launcher, with uv inline script metadata |
| `cli.py`, `__main__.py` | command line front-end |
| `config.py` | YAML configuration and validation |
| `scanner.py` | the scan itself: GraphQL documents and caching decisions |
| `ghclient.py` | GraphQL transport: rate limits, retries, adaptive page sizes |
| `ghtypes.py` | typed coercions for the JSON that comes back |
| `cache.py` | persistent per-organization cache |
| `snapshot.py` | data model, and the on-disk YAML schema |
| `writer.py` | snapshot writing and rotation |
| `orgscanner.yaml` | annotated sample configuration |
