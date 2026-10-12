# Control Center read-only diff viewer

Date: 2026-10-07

Status: Authorized read-only diff implementation complete; all required gates passed.

The user selected an embedded read-only viewer rather than a full review workspace.
Artifacts now opens the viewer on demand, with changed-file search/navigation,
numbered unified and desktop split views, coloured additions/removals, basic syntax
colouring, three-line context hunks and explicit line-ending/final-newline markers.
Mobile uses unified view. Failed reads offer a scoped retry.

The typed `/api/v1/workbench/diff` query accepts project/node/revision/artifact and
a file index. It never accepts a filesystem path. Application and adapter checks
verify scope, snapshot freshness, ChangeSet identity/base bindings and proposed
content hashes before returning server-generated hunks. Reads are authenticated
and require the existing inspection/evidence capabilities. Reconciliation and
selection changes cancel superseded requests.

Base content is the immutable Git blob from the recorded base revision, not the
current source file. The guarded staging workflow requires a clean base. The
viewer does not reconstruct historical uncommitted source; checkout conversion
may differ from Git blob line endings, which are shown explicitly. Git metadata
inspection disables optional locks, fsmonitor, automatic lazy fetch, interactive
credential prompts and transport protocols. Missing objects stay unavailable.
The lazy-fetch boundary follows [Git's documented behavior](https://git-scm.com/docs/git-upload-pack/2.43.4).

Preview limits are 32 KiB per side and 4,000 combined lines. Binary/non-UTF-8,
protected, missing, unsupported-mode/rename or oversized content returns an
explicit unavailable preview, without partial hunks. Rendering uses interpolated
text spans and CSS variables, with no executable HTML, editor dependency, comment
store, review submission or approval channel. Source files are never written.

## Verification

| Gate | Result |
|---|---|
| Focused exact-base/HTTP/content tests | 13 passed |
| Angular unit tests | 14 passed in 7 files, including cancelled reads, safe rendering, split pairing and scoped retry |
| Production browser | Passed; split/unified switching, mobile reflow and inert markup; desktop/mobile captures inspected |
| Production build | Passed; initial 538.73 kB raw / 110.30 kB estimated transfer, viewer deferred until interaction |
| `uv sync --all-groups` | 69 resolved, 68 checked |
| Ruff / formatting | Passed; 257 files formatted |
| Mypy | 120 source files passed |
| Doctor | Exit 0, status `ok` |
| Full Python suite | 595 passed, 3 skipped in 1236.73s, including actual loopback/Chromium integration |
| Wheel / whitespace | Built; all 64 production assets and current Git inspection code match source bytes; `git diff --check` passed |

Tests verify CREATE/MODIFY/DELETE, immutable base after working-file changes,
CRLF/final newline preservation, credential/binary/size/line budgets, foreign/stale
scope, negative indices, tampered proposed bytes, actual HTTP authentication and
the no-fetch/no-prompt environment. No provider credentials or remote network are
required. Windows Chromium evidence retains the common GUI's stated acceptance
limits; it is not all-browser or accessibility certification.

See [operations](../docs/control-center.md), [architecture](../docs/architecture.md)
and the [GUI completion report](control-center-implementation-report.md).
