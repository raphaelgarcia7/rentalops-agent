# ROP-010 — quotations-v1 delivery evidence

## Revision and scope

Executor: `gpt-6.1-sol`, reasoning `high`, agent `/root/rop010_executor`.
Approved issue #10 revision: `2026-10-04T00:13:33Z`; UTF-8 body SHA-256:
`a840a353fec36d107720e2d5e5e62c4fab5fc0ea856591633ebd7919ca3ed4d9`.
The executor fetched the issue through the GitHub connector and compared its complete
body with the approved local snapshot, removing only the snapshot's terminal LF:
exact body and SHA-256 matched. No issue-body edit was made.

Base: `6623b5c054a2c3210caaa8aa3bf430186d373df9` (`origin/develop` supplied by coordinator).
Implementation SHA: `efe16dd300769fb3e897b7f104757f63afe844ac`.
Branch: `codex/10-quotations`. This document is a subsequent documentation-only commit;
the coordinator must obtain independent review against the exact final HEAD and base.
Validation below ran against the complete implementation tree represented by that
implementation SHA. No dependency versions changed.

Only this approved quotation slice was implemented: immutable commercial versions,
server money/dates/demand, authenticated private APIs, safe repetition/concurrency,
real responsive UI and customer quotation history. No payment, stock allocation,
pre-payment hold, reservation, real contract, assistant/AI or deployment was added.
R08-INACT is implemented here. R10-OVERLAP remains required in issue #11: the present
capacity query is explicitly **registered stock**, not calendar availability.

Dependencies #3/#7/#21/#8/#9, Project In progress, the single-executor lock and the
unchanged remote approved revision were verified by the coordinator before dispatch
and resume. Owner remains `rop010-quotations-20261003-c904e38b`; the executor neither
released it nor published a branch/PR. Initial actual usage-limit interruption
occurred before edits; the same execution resumed after ordinary quota was available.
No credits, account switch, model substitution or paid API fallback was used.

## Acceptance evidence

Paths below are relative to this repository. All test data are synthetic.

| AC | Local evidence and outcome |
| --- | --- |
| AC10-01 | `test_quotation_api.py::test_real_auth_csrf_statuses_private_replay_and_actor`, the full real-browser flow in `quotations-live.spec.ts`, and customer history through `CustomerQuotations.tsx`: real session/create/read/revise, linked existing minimum customer, optional times, kit and product lines. No CPF, photo or contract required. |
| AC10-02 | `test_demand_money_pending_no_stock_effect_snapshot_history` proves 2 arches/5 vases and kit's own price; `test_custom_composition_price_explicit_and_catalog_unchanged` proves explicit custom price, effective composition, aggregate demand and unchanged catalog. Browser proves customization demand 7 vases, apt 4, shortage 3. |
| AC10-03 | Three inactive integration cases (product/kit/component) reject new offers and revisions while historical versions remain readable. Catalog stale test returns 409. Retained-line revision preserves original agreed values; browser v6 updates catalog sources only through explicit action and preserves v1. A component regression blocks that action until current options are available. |
| AC10-04 | Capacity/no-side-effect integration tests, repeated reads and real browser shortage save. Stock and maintenance are untouched by quotation writes; UI says budget does not reserve stock and calendar is not considered. No payment/reservation mutation exists. R10-OVERLAP is carried forward, not waived. |
| AC10-05 | `test_date_and_time_contract` and `test_same_day_optional_times_local_inclusive_validity_and_return_day`: equality, optional/coherent HH:mm, host-independent UTC clock around São Paulo midnight, inclusive validity, return day 13/next day 14. `test_database_immutability_money_quantity_fk_and_guard` rejects expired/stale guard calls. Browser saves expired v4, visibly preserves it and renews with reason to v5. |
| AC10-06 | Parameterized exact-total tests cover 400 with 40/10%, 100.01, 0.05 at 10%, total 0.01, zero/excess/negative/float/nonfinite/precision/percent/overflow boundaries and deposit+balance equality. One discount; no client-calculated money accepted. Numeric(12,2), Decimal, JSON money strings, HALF_UP discount and ceil-half deposit. |
| AC10-07 | `test_concurrent_revisions_one_winner`, stale catalog/version test, rollback commit-failure test, source-preserving history and DB immutable-record tests. One concurrent revision wins; losing transaction changes no header/snapshot/audit. Browser compares current version, preserves human draft/reason and never silently accepts catalog changes. |
| AC10-08 | Real PG migration after 0005: upgrade, repeated upgrade, complete metadata parity, indexes/FKs, downgrade only quotation objects, re-upgrade. Direct SQL quantity/money/reference/position/source constraints and UPDATE/DELETE immutability tests. Sequential and concurrent create/revise replay produce one result/audit; changed body with same UUID returns 409. Entire auth/catalog/customer suite remains included. |
| AC10-09 | Real-auth API status tests cover 401/403/404/409/422/503, trusted Origin for every POST, no-store, stable IDs and actual session attribution. Search is body-only with page/order/client filters tested. Internal fields rejected without value echo. Application/access/error logger and safe DB-error regressions described below. Unknown network save is reconciled with the same UUID/body; no false success. |
| AC10-10 | 8 quotation browser cases (2 scenarios × 4 widths) inside the final 100-case production Chromium suite. Real API/auth/PG: initial offer, custom kit, discount, maintenance shortage, saved offer/customer history, ordinary revision, stale catalog and revision conflicts, unknown-result replay, expired/renewed versions, reauthentication preserving draft, capacity refresh, explicit catalog-source update. Separate controlled loading/empty/503/retry/keyboard/reduced-motion states. Each quotation visual checkpoint has zero horizontal overflow and zero axe violations. 48 masked captures generated; selected inspection below. |
| AC10-11 | Complete local pipeline and scans below passed without skip or disabled assertions. Existing migration-specific customer test now targets its own 0005 revision, preserving all original customer assertions; quotation migration separately checks latest full metadata. Remote checks/protections are coordinator gates, not executor claims. |
| AC10-12 | **Pending coordinator**, not Done: independent `gpt-6-sol/high` review of exact final head/base after executor stops; PR publication/attachment, existing remote gates, protected squash to develop, confirmed merge/Project Done/final journal. No main merge or deployment. |

## Final local commands and results

Windows PowerShell; checkout
`C:/Users/Raphael/.codex/worktrees/rentalops-customers/rmg-chatbot`.
Frontend commands run from its `frontend/` directory. All commands below exited 0.
No assertions were skipped or weakened to pass.

| Command | Exact result |
| --- | --- |
| `uv sync --project backend --locked` | 89 resolved / 88 checked; existing lock reused. |
| `uv run --project backend ruff check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | All checks passed. |
| `uv run --project backend ruff format --check backend C:/Projects/praxis/rmg-chatbot/infra/automation C:/Projects/praxis/rmg-chatbot/infra/tests` | 54 files already formatted. |
| `uv run --project backend mypy backend/src` | Success, 22 source files. |
| `$env:TEST_DATABASE_URL='postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test'; uv run --project backend pytest backend/tests C:/Projects/praxis/rmg-chatbot/infra/tests -q` | **283 passed, 2 warnings, 179.29s**; includes real PG integration and shared infrastructure tests. |
| `uv export --project backend --locked --all-groups --no-emit-project --format requirements-txt -o C:/Users/Raphael/.codex/tmp/rop010-audit-requirements.txt` followed by `uv run --project backend pip-audit --disable-pip --no-deps -r C:/Users/Raphael/.codex/tmp/rop010-audit-requirements.txt` | No known vulnerabilities; full lock export retained hashes/pins. |
| `npm ci` | 243 installed / 244 audited, 0 vulnerabilities. |
| `npm run lint` | ESLint passed. |
| `npm run format:check` | All matched files use Prettier style. |
| `npm run test` | **5 files, 44 tests passed**, final 13.64s. |
| `npm audit --audit-level=high` | 0 vulnerabilities. |
| `npm run build` | TypeScript/Vite passed; 120 modules; CSS 20.61 kB (gzip 4.89), JS 340.49 kB (gzip 101.58); final Vite 1.00s. |
| `$env:TEST_DATABASE_URL='postgresql+psycopg://rentalops_test@127.0.0.1:15437/rentalops_test'; npm run test:e2e` | **100 passed, 2.8m**, no retry configured. Uses already-built production output through Vite preview, real disposable API/PG. |
| `git diff --check` and `git diff --cached --check` | Passed. |
| `gitleaks.exe git --pre-commit --staged --redact --no-banner .` | No leaks, implementation staged diff ~179.30 kB. |
| `gitleaks.exe git --redact --no-banner --log-opts=--all .` | No leaks, initial 20 commits / ~2.24 MB. |
| `gitleaks.exe git --redact --no-banner --log-opts=6623b5c054a2c3210caaa8aa3bf430186d373df9..HEAD .` | No leaks, implementation commit scanned. Final documentation HEAD is scanned again at handoff. |

Gitleaks executable reused from
`C:/Users/Raphael/.codex/tmp/rop007-postgres-20261003-5d9bf762/gitleaks/gitleaks.exe`.
Dependencies/audits are a point-in-time check, not a guarantee against future findings.

Warnings preserved: Starlette's existing TestClient/httpx deprecation and anyio
BlockingPortal alias deprecation (2 pytest warnings); Playwright child processes
warn that FORCE_COLOR overrides NO_COLOR; pip-audit warns about `--no-deps` and
encourages hashed pins (the audited lock export contains hashes); Git reports
configured LF-to-CRLF normalization. No production-build warning occurred.

## Original failures and corrections

- First immutable-trigger assertion expected `OperationalError`; PostgreSQL's
  user-raised P0001 produces `ProgrammingError`. The assertion was corrected to
  the real driver error, not removed. Initial focused result: 41 passed / 1 failed.
- First privacy run enabled INFO capture for every logger. The test client's
  `httpx` INFO request message contained
  `HTTP Request: POST http://testserver/quotations/search?name=PRIVATE_SYNTHETIC_DO_NOT_ECHO`
  (followed by its status), triggering the sentinel assertion. This is the client
  library logging the intentionally invalid synthetic URL, not server logging of
  a body. The final test captures the actual production namespaces
  `rentalops_api`, `uvicorn.access`, `uvicorn.error` at INFO, the same scoped policy
  as the customer regression. No application/access/error logger was excluded or
  disabled to pass; sentinel absence in all captured server logs and every error
  response is still asserted, including forced SQL exception/503. Application
  services/routes do not log body, negotiated reasons, contacts or SQL errors;
  audit rows contain metadata/IDs/field names, not free-text payloads. Initial
  focused result was 54 passed / 1 failed. Reviewer should independently assess
  this logger-scope correction; upstream proxy/server deployment logging has not
  been certified. The disposable harness has its pre-existing access_log=False,
  warning-level policy; this was not a change to make the privacy test pass.
- Initial Vitest regression still expected the old empty rental-history text
  after real quotation history was integrated: 37 passed / 1 failed. Corrected
  the assertion to the new truthful confirmed-rental empty state; added quote
  history mocks/meaningful assertions. Final suite is 44/44.
- Initial quotation browser cases (4/8 failures) exposed accessible names that
  inherited the full nested native select option text. Added explicit aria-labels
  to selects/textareas while keeping real visible labels.
- A focused real browser case sent logout without the authentication contract's
  `{}` JSON body (1 passed / 1 failed); corrected test to the existing real auth
  contract, not an app/auth change.
- First full browser matrix: 92 passed / 8 failed. The real quotation empty page
  duplicated the shell return link, and an explicit-source refresh button could
  be clicked before the catalog options loaded, silently doing nothing. Removed
  only the duplicate nested link; disabled refresh until options/current source
  are available and added a delayed-options component regression. All original
  expected behavior remains asserted. Both full subsequent matrices passed 100.
- During final rerun the operator supplied `RENTALOPS_TEST_DATABASE_URL` instead
  of required `TEST_DATABASE_URL`. The safe fixture failed before connection/DDL:
  194 passed / 1 failed / 88 setup errors; browser harness startup was refused.
  Correct variable reruns produced 283/283 and 100/100 above. No unsafe fallback
  database was used. A cleanup read-only command also hit PowerShell quoting
  parser error before execution; corrected read-only query passed.

## Visual and interaction evidence

Real Chromium production browser at 320×740, 390×844, 768×1024 and 1440×1000.
Each project generated these 12 quotation phases under the ignored local directory
`frontend/test-results/evidence/`:
`preview-shortage`, `catalog-conflict`, `customized`, `saved`, `revision-conflict`,
`expired`, `renewed`, `explicit-catalog-update`, `loading`, `empty`, `error`, `keyboard`.
Thus **48 quotation PNGs**, preserved locally for reviewer inspection, not uploaded
to a public issue. Production HTML report is `frontend/playwright-report/index.html`.
Synthetic names/reasons only; customer contacts and `.catalog-attributes dd` values
are masked. The broad existing attribute mask also hides money/date summary values:
their correctness is asserted in browser DOM/API/unit tests, not inferred from the
masked pixels. No real customer data, private real-access link or signature was used.

Six final screenshots were opened and visually inspected by the executor:

| Capture | SHA-256 |
| --- | --- |
| `mobile-320-quotations-preview-shortage.png` | `dce2661c13bbc1455e646b52e6a77bccbd5729c3bda077731a16e3cfcdf8018c` |
| `mobile-320-quotations-revision-conflict.png` | `73a754d7de298084d2ed408f2210b2b56c43cb4260399aa33a5e3399525eff1b` |
| `mobile-390-quotations-preview-shortage.png` | `003f18b2bfbf26ff46a4b73b92716bb3c3a50cb8ab518e0f78d90ce708737156` |
| `mobile-390-quotations-keyboard.png` | `ae7071fd315251f04a62b22608e7b8f541fe20801a2e24e64b9f78af21332718` |
| `tablet-768-quotations-customized.png` | `da2c4d3942c62c7772d8468f4505deacbecf29237e54b44fd57ba2aab21f0276` |
| `desktop-1440-quotations-explicit-catalog-update.png` | `c397334a3c86a17ea56fa4901536431f9baea678ffaba2ff2451e54fd7a66c6b` |

Observed: shell navigation reflows on mobile; fields and actions do not clip;
shortage and non-reservation warning remain distinct; conflict comparison precedes
the retained draft with separate keep/reload actions; tablet fields use two columns;
desktop retains shell/sidebar and readable offer/history column; mobile keyboard
focus ring is visible. The complete editor/history is intentionally vertically long,
especially on 320 px, and requires scrolling. Native date/time controls use the
browser's locale display while submitting validated ISO/local strings. Loading,
error, empty, heading focus, keyboard navigation and reduced-motion assertions ran
at all four widths. Only six representative captures were manually inspected; this
is not a claim that every pixel/state/device was manually tested or an accessibility
certification. No Safari/Firefox, physical touch hardware or screen-reader session
was tested.

## Persistence safety, reproducibility and handoff

Real disposable PostgreSQL **17.10**, loopback `127.0.0.1:15437`, database/user
`rentalops_test`; no production/local-development account changed. Fail-closed target
validation precedes DDL. All fixture/harness schemas have validated unique UUID
names; teardown drops only their owned namespaces/storage. Final read-only check
after both suites: **0 remaining rentalops_test_* schemas; 0 other connections**.
API port 8000 and production-preview port 4173 are no longer listening. The inherited
disposable PostgreSQL process PID 52696 on 15437 remains available for independent
review; it was not created or stopped by this executor. No test/preview service is
left running and no root `.env` was overwritten.

The checkout at this base does **not** contain the canonical versioned standards,
business-rules, codex-delivery, ADR-001 or shared automation/infra tests that currently
exist only in the user's dirty root. The executor read those approved root guidance
files completely, read-only; followed their applicable rules and ran root infra tests
without copying unrelated accumulated scaffold into this task. This is a clean-clone
reproducibility/documentation gap, not a claim that those files were versioned by this
delivery. Only quotation-specific rules were added in `docs/product/quotation-rules.md`;
previous human rules were not replaced. README records endpoints, setup/migration and
the new commercial behaviors. No speculative repositories, scheduler, graph or AI
layers were introduced; business rules remain in framework-independent services.

Local application work and AC10-01–11 evidence are ready for independent review.
AC10-12, remote checks/protections, final PR attachment/merge and Project Done remain
the coordinator's required gates. Absence of remote CI/protection is not a passed
check; coordinator must inspect and record actual remote state. The executor stops
after clean local commits and exact final SHA/journal checkpoint; lock remains owned.
The coordinator confirmed Project **Validating** after local implementation finished;
the task is not Done until the authorized review/integration workflow is complete.
