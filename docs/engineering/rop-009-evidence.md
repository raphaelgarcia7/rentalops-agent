# ROP-009 — customers-v1 evidence

## Scope, approval and revision

- Approved issue: [#9](https://github.com/raphaelgarcia7/rentalops-agent/issues/9), `customers-v1`, `updated_at=2026-10-03T14:02:37Z`.
- Exact approved UTF-8 body SHA-256: `83ed04f04754c053b04688f5de442844f8524f71c074f60fd70ec67c60172e66`. Re-fetched unchanged before handoff.
- Base: `e1217093afdb8722472bb57cc0dbed1a564af1a2` (catalog PR #25 integrated). Coordinator verified direct/transitive prerequisites #3/#7/#21 Done and remotely merged before dispatch; this execution did not waive those gates.
- Implementation SHA: `62e307bc657787933f7b5a889d1a9015dc0bc38b`, branch `codex/9-customers`. The following evidence-only commit changes no executable code. Resolve the final review head with `git rev-parse HEAD`; the coordinator records that exact SHA in the handoff/journal.
- Isolated checkout: `C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot`. Shared root was used for guidance/automation checks, not copied wholesale or published.
- Sole executor: `gpt-6.1-sol/high`; lock owner `rop009-customers-20261003-4fb81199`, task `issue9`, confirmed before edits and at handoff. No lock release, GitHub writes, push, PR, merge, main/deploy changes or successor execution by this executor.

Read guidance: shared-root AGENTS.md, engineering standards/delivery workflow, business rules, modular architecture decision, checkout README and complete approved issue. Changes stay within customers, existing shell integration and regressions, incremental migration and documentation. Independent `gpt-6-sol/high` review of the exact final SHA and remote publication/checks/merge remain coordinator gates; this document is not a review or Done claim.

## Contract and implementation

Customer uses stable UUID, required trimmed name and normalized string phone, optional validated email/notes/CPF/RG/progressive address, UTC timestamps, session-derived actors and integer version. `phonenumbers 9.0.40` supplies Brazil-default/international E.164 normalization; no WhatsApp verification/message delivery. Contracts forbid arbitrary IDs/actors/timestamps/internal version/CNPJ. Field lengths and address formats are in the README and typed contracts.

PostgreSQL `0005_customers` adds customers and metadata-only audit, nullable `UNIQUE` CPF, name/UUID and contact indexes and persistence checks. CPF is normalized/validated including checksum and repeated digits. Database uniqueness, not a pre-query, resolves concurrent creation/edit. After rollback a conflict returns the existing UUID only behind real authentication. No phone uniqueness, automatic merge, hard deletion, roles, financial operations or fictitious rentals.

`acknowledged_shared_contact` is a typed list of UUIDs shown by the last warning, not a blanket boolean. A short transaction advisory lock derived in memory from the normalized phone serializes check/write for that target contact. Current matching IDs must be included in the acknowledgement; a newly appearing ID causes another 409 warning. Hash/contact values are not logged or persisted as audit metadata. Edits to an unchanged contact do not prompt unnecessarily. Tests cover both concurrent creations and concurrent contact edits.

PATCH requires `expected_version`; atomic ID/version UPDATE prevents lost writes, with 409 and no partial update/audit on conflict. Top-level omissions and nested address omissions preserve previous data; `address: {}` preserves it, explicit blank/null clears only a member, and `address: null` clears the address. Audit stores client/actor/session IDs, UTC time, version and changed field names, never copies of documents/contact/address.

Authenticated routes are POST `/customers`, GET/PATCH `/customers/{id}` and POST `/customers/search`. Existing real session and Origin/CSRF boundary is reused, including POST search. Search filters remain in JSON body, text name search escapes wildcards, phone/CPF match normalized values exactly, page size defaults to 25/max 100, order is name/UUID. Summary returns only ID/name/phone/version. Query strings on customer routes are rejected without echoing them. Success/handled failures use private caching; 422 names known fields without rejected values; 401/403/404/409/503 do not expose SQL, payload or stack traces.

UI reuses shell/tokens/catalog form primitives. Progressive list/search/pagination/new/detail/edit, explicit shared-contact confirmation, consultation in another tab preserving the form, duplicate CPF links, current-version comparison and deliberate keep-draft/reload choices are implemented. Expiration/re-authentication preserves the in-memory edit; no local-storage persistence of PII. Stable `/clientes?cliente=<UUID>` is ready for future rental links; history explicitly remains empty until #10.

## Acceptance matrix

| Approved criterion/matrix | Evidence |
| --- | --- |
| Restricted create/list/edit/detail and real identity | `test_customer_api.py`: real AuthService login, 401 on every route, absent/wrong Origin, second authenticated actor, server session in audit, 404 and forbidden internal fields. `customers-live.spec.ts`: real login, edit, logout/re-login with draft preserved. |
| Minimum/progressive PF, optional fields, limits/normalization | `test_customer_contracts.py`: 38 parametrized cases; `test_customers.py`: minimum/progressive ID/version/UTC/actor/audit and nested-address preservation/explicit clearing. Unit Brazil/international phone and document/field validation. Live UI creates minimum and adds CPF/city/UF later. |
| Shared contact warning, explicit distinct person, no merge | Service/API and live browser warning/acknowledgement; stale observed contact set causes fresh warning; concurrent create/edit phone tests produce one initial success and one warning. Distinct UUIDs retained. |
| CPF unique including creation/edit races; null allows multiples | Real PostgreSQL constraint and direct SQL rollback assertions; duplicate create/edit and `create_cpf`/`edit_cpf` two-thread races. API 409 IDs/no document echo; browser preserves form and consults original in another tab. |
| PF only/no CNPJ; stable rental link/true empty history | Extra CNPJ rejected; no company/delete/rental API/model added. Same customer UUID after edits and stable link asserted; live detail shows no fictitious rental. |
| Migration upgrade/repeat/rollback, metadata/atomicity | Exact customer head `0005_customers`, metadata parity, repeated upgrade, rollback to catalog preserving prior tables, re-upgrade; direct checks/foreign keys/nullable unique; injected create/edit commit failure leaves data/audit unchanged. Legacy catalog migration test explicitly targets its own `0004_catalog` and retains exact assertions, not a relaxed head check. |
| Search limits/order/body-only, auth/versions/rollback | Real 28-record PostgreSQL ordering/paging/escaped wildcard/exact filters, default/max/rejected invalid page types; live 26-record page 25+1; body URL assertions and actual invalid query rejection. Version race permits one write; conflict keeps form and compare/reload. |
| UI states/focus/responsiveness/reduced motion/axe | 8 customers cases (2 scenarios × 4 widths), 40 customer axe/overflow checkpoints, 40 masked/synthetic captures. Controlled loading/error/retry/empty, error focus, progressive keyboard, 3px focus outline, cancel focus; production real flows plus all existing auth/catalog/shell regressions. |
| Privacy and secure failures | API tests capture application/Uvicorn loggers at INFO for invalid body/query and 409/503 paths; no document/contact/SQL echo/log. Audit assertion allows only metadata. `test_customer_privacy.py` executes harness entrypoint with `uvicorn.run` mocked, asserting loopback/access_log=False/proxy_headers=False/warning exactly. Actual browser harness output has no request lines or personal values, including rejected filter-in-URL requests. No LLM/traces/analytics introduced. |

## Commands and observed results

Commands run from the checkout unless noted. Test database only: official disposable PostgreSQL 17.10, `127.0.0.1:15437`, database/user `rentalops_test`, `TEST_DATABASE_URL=postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test`. No password, real service/account/data, migration against development or unowned cleanup used. UUID schemas are created/dropped by existing fail-closed fixtures; browser temporary photo storage is owned by its harness.

| Exact command | Result |
| --- | --- |
| `uv sync --project backend --locked` | Resolved 89 packages, installed/checked 88. |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | Passed. |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | 45 files already formatted. |
| `uv run --project backend mypy backend/src` | Passed, 18 source files. |
| `uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests` | Final implementation SHA: 233 passed, 2 warnings in 58.09s, including shared infrastructure and harness-privacy regression. |
| `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt -o C:/Users/Raphael/.codex/tmp/rop009-audit-requirements.txt --quiet` then `uv run --project backend pip-audit -r C:/Users/Raphael/.codex/tmp/rop009-audit-requirements.txt --disable-pip --no-deps` | No known vulnerabilities, including development dependencies; no exemptions. |
| In `frontend`: `npm run lint`, `npm run format:check` | ESLint/Prettier passed on final frontend tree. |
| In `frontend`: `npm run test -- --run` | 38 passed, 4 files, 17.14s. |
| In `frontend`: `npm run build` | TypeScript/Vite passed; 113 modules, CSS 19.06 kB, JS 314.20 kB (96.17 kB gzip), no build warning. |
| In `frontend`: `npm audit --audit-level=high` | 0 vulnerabilities. |
| In `frontend`, same safe `TEST_DATABASE_URL`: `npm run test:e2e` | Final 92 passed in 2.1 minutes, retries=0; all 4 Chromium projects (320×740, 390×844, 768×1024, 1440×1000). Includes 8 customer cases and 40 zero-violation customer axe checkpoints tagged WCAG2A/AA, 2.1AA and 2.2AA, plus existing auth/catalog/shell. |
| `git diff --check`, `git diff --cached --check` | Passed; Git emitted LF→CRLF checkout-policy warnings, not whitespace errors. |
| `gitleaks.exe git --pre-commit --staged --redact --no-banner .` | Implementation staged scan ~114.62 kB, no leaks. |
| `gitleaks.exe git --redact --no-banner --log-opts='--all' .` | Implementation head: 18 commits, ~2.10 MB, no leaks. |
| `gitleaks.exe git --redact --no-banner --log-opts='e1217093afdb8722472bb57cc0dbed1a564af1a2..HEAD' .` | Implementation range: 1 commit, ~114.62 kB, no leaks. Final documentation/staged/history/range scan recorded before handoff. |

Gitleaks binary: `C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/gitleaks/gitleaks.exe`; scans target tracked changes/history, not ignored virtual environment. Audit export is temporary/untracked and includes no credentials.

Warnings preserved: Starlette TestClient deprecates httpx in favor of httpx2; AnyIO BlockingPortal alias is deprecated. pip-audit emits its standard fully-hashed-pins recommendation for `--no-deps`. Node Playwright workers report NO_COLOR ignored because FORCE_COLOR is set. None was hidden, treated as a failed check, or fixed through an unrelated dependency migration.

## Visual inspection and limitations

Local evidence directory (ignored, preserved for reviewer):
`C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot/frontend/test-results/evidence/`.
HTML report: `frontend/playwright-report/index.html`. There are 40 customer captures, six real-flow phases and four controlled-state phases at each width; contact/document/address values are masked at capture time, names/notes are explicitly synthetic. No real credential or document capture is published/tracked.

Final-run representative captures manually opened and inspected:

| Width | Capture | Observed |
| --- | --- | --- |
| 320 | `mobile-320-customers-keyboard-validation.png`; `mobile-320-customers-loading.png` | Single-column progressive form; visible CPF focus ring and usable labels/buttons; loading text/navigation wraps without clipping or horizontal scroll. Error focus was asserted before the phone was cleared for the screenshot. |
| 390 | `mobile-390-customers-shared-warning.png`; `mobile-390-customers-cpf-conflict.png` | Warning, existing-record link, explicit distinct-person action and retained form readable; CPF conflict has no override action. Long progressive form scrolls vertically. |
| 768 | `tablet-768-customers-version-comparison.png`; `tablet-768-customers-list-page2.png` | Current-version values and separate keep/reload actions clearly separated from retained draft; two-column form/comparison and stable pagination fit without overlap. |
| 1440 | `desktop-1440-customers-form.png`; `desktop-1440-customers-minimum-detail.png`; `desktop-1440-customers-error.png` | Shared sidebar/shell and form spacing coherent, focus clear, success/empty-rental history/audit distinguishable, error/retry visible. |

The four representative keyboard/warning/comparison/form captures were inspected again after the last complete browser run replaced them. Additional phases were inspected during the preceding complete green run; source/rendered layout was unchanged by the final privacy-test-only additions. Screenshot masking intentionally hides value typography in document/address details; usable unmasked synthetic names/notes and automated DOM interactions supplement it. This is actual production Chromium inspection at four widths, not all-device certification or a substitute for human assistive-technology testing. Safari/Firefox/native screen readers and a real external proxy/deployment were not tested.

## Failures investigated, not skipped

Early customer browser iterations exposed unstable accessible names on the search select and filled notes textarea; explicit label IDs fixed them. Error alert focus initially used requestAnimationFrame and was intermittent; a committed-render effect fixes it, with regression assertions. Re-authentication test initially selected both visible login email and the hidden retained draft email; the exact visible textbox selector fixes test ambiguity while preserving the draft requirement. Initial focused browser runs reported 4, then 5, then 4 failures; all were investigated before the full rerun.

The first complete regression reported 91 passed/1 failed: mobile-390 catalog kit review queried `needs_review` before PATCH completed. Trace metadata showed PATCH starting at `23:16:59.400Z`, GET at `.437Z`, subsequent refreshed kit list at `.488Z`. A substring heading matched the editor heading, so it was not a committed-save signal. Test now waits for the PATCH, asserts status 200 and response `needs_review=false`, waits for the exact detail heading, and retains the database-backed GET assertion. No catalog business rule changed, no retry/skip/relaxed assertion. Complete reruns passed 92/92 twice, including the strengthened test and final invalid-query test.

The added harness-privacy entrypoint regression initially failed import resolution because pytest uses backend as its root; it now explicitly prepends the repository path using pytest's reversible monkeypatch. It passed focused and is included in the final full count.

A proposed extra standalone process/log-capture probe was rejected by command safety policy before execution; it was not run, retried through another mechanism or claimed as passed. Privacy evidence instead uses the existing authorized harness/pipeline, real invalid-query browser calls, secure error-path API logs and deterministic Uvicorn entrypoint settings. No assertion about upstream proxy/access logging is made: any future proxy must preserve the documented no-body/no-query/no-PII logging policy. Unhandled third-party infrastructure failures and actual production operational retention/backup remain outside this local gate; retention is #4.

## Handoff resources

Browser harness teardown passed; owned API/preview no longer listen on 8000/4173. Read-only PostgreSQL cleanup verification after the final full suite returned `remaining_test_schemas=0` and `other_test_connections=0`; no matching harness temporary storage directory remains. The check explicitly queries only the loopback test database using pg_namespace and pg_stat_activity, with no deletion. Disposable PostgreSQL cluster PID 52696 is intentionally retained for independent review; the real Windows PostgreSQL service/data were never touched. Ignored visual evidence/report and disposable development environments remain available. Coordinator retains the unique lock/journal; executor stops after clean SHA handoff, with no new implementation or external publication.
