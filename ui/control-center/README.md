# Control Center development

This Angular 21 application ships as offline assets in the Python package. It
queries a typed common workbench boundary; migration-specific behavior stays in
the backend adapter. See [operations](../../docs/control-center.md) and the
[optional project definition](../../docs/project-work.md).

## Structure and conventions

- `core/`: session, HTTP errors, route guards, preferences and application errors.
- `shared/`: reusable status, feedback and native modal components.
- `workbench/`: route-scoped store/API, explorer, shell and lazy feature pages.
- `app.routes.ts`: project binding and entry routes; `workbench.routes.ts`: item
  sections, runs and health. Route/query parameters own selection and artifact pins.

Standalone components use OnPush and Angular's zoneless change detection. Signals
own local state and computed projections; RxJS handles cancellable HTTP reads,
debounced search and polling, with destruction cleanup. Typed models cross the API
boundary. Feature routes provide their store; shared components do not fetch data.
Templates use native links, controls and dialog semantics with explicit feedback.

Artifacts defers the reusable read-only diff viewer until interaction. Its typed
per-file query binds project/item/revision/artifact and file index. Context hunks
are bounded; base blobs come from the recorded Git revision, not current source.
Code highlighting uses interpolated text spans with no HTML injection or additional
editor dependency. Split rows are a presentation projection of server diff lines;
mobile uses unified rows. No review-write or approval endpoint is introduced.

Bootstrap utilities and plain CSS variables meet the current styling needs. SCSS
would add no useful abstraction here. Theme preferences persist no credentials.
Session authentication stays in memory/cookies and server gates remain independent.
The build disables critical-CSS inlining to preserve the strict script CSP; do not
enable generated inline stylesheet handlers without verifying the actual browser.

These conventions follow the Angular [style guide](https://angular.dev/style-guide),
[zoneless guidance](https://angular.dev/guide/zoneless),
[routing](https://angular.dev/guide/routing) and
[HTTP testing](https://angular.dev/guide/http/testing). Use the compatible Node and
TypeScript ranges in [Angular's version table](https://angular.dev/reference/versions).

## Build and validate

```text
npm ci --ignore-scripts --no-audit --no-fund
npm run lint
npm run format:check
npm test
npm run build
npm run test:e2e
```

Unit tests use Angular TestBed, HTTP testing and Vitest without network access.
The production browser journey uses locally installed Chrome/Chromium and
`playwright-core`; set `CHROME_BIN` if required. Build output goes directly to the
Python package's `src/migration_agent/ui/static`. Generated test screenshots stay
in the ignored `tests/artifacts` directory. The repository's Python quality gates
also exercise the actual loopback server and canonical workflow store.

## Development server

First launch `uv run agent ui /path/to/project` normally on `127.0.0.1:8080` and
authenticate in the browser it opens. Then run `npm start` in this directory and
open `http://127.0.0.1:4200` in that same browser. The development proxy forwards
only `/api/**` to the loopback backend and translates its local Origin. Use
`127.0.0.1` consistently so the host cookie can be reused; it is not a localhost
cookie. Backend capabilities, independent CSRF, approval and freshness checks
still apply. Production serves the compiled bundle directly and uses no proxy.

GUI source inspection never writes the selected repository. Edit project-work
definitions in Git before staging, then review/commit them through your ordinary
workflow. Runtime state and staging roots remain outside source.
