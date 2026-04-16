# WildLifeLens Operations Suite

Fully offline Flask + SQLite + HTMX system implementing:

- **Auth & RBAC:** Session-based authentication (bcrypt), 5-role RBAC
  (`admin` / `staff` / `photographer` / `kitchen` / `member`), admin-only user
  role management, CSRF-token protection on views + JSON-content-type
  enforcement on APIs (blocks CSRF via cross-site form POST, including
  bodyless mutations like `logout`).
- **ABAC overlay:** Admin-configurable `ScopePermission` grants with seven
  scope types — `location`, `station`, `employee`, `field`, `record`, `menu`,
  `api` — layered on the static RBAC matrix, enforced uniformly via the
  `@permission_required(..., record_scope=True)` decorator plus dedicated
  field/record checks in financial endpoints.
- **Members:** PII encrypted at rest with Fernet; indexed HMAC-SHA256
  `phone_hash` for fast O(log n) lookup; tier metadata (description + benefits
  list + max-discount %) surfaced in serializers and lookup UI; explicit
  `field`-scope grants unmask individual fields for specific roles.
- **Orders:** Full lifecycle with strict state machine
  (`created → paid → in_prep → ready → delivered → reviewed`, plus the
  `ready_for_pickup` reconciliation branch); integrated checkout with points
  redemption (1 pt = $1, 20% cap) and printable receipts; redemption failures
  surfaced to UI/API (no silent swallow); autonomous expiry via background
  ticker + `flask check-expiry` CLI.
- **Scheduling & Bookings:** Photographer schedule (working/break/off);
  schedule-aware booking rejects `break`/`off` overlaps and off-hours;
  conflict detection with 5-minute booking lock; calendar grid UI.
- **KDS:** Station routing derived from order item categories
  (`drink→bar`, `grill→grill`, `dessert→pastry`, etc.); explicit
  `late by N min` lateness alert; completion write-back to order events +
  auto-advance to `ready` when all tickets complete; allergy-flag propagation.
- **Search:** Keyword + synonym + pinyin fuzzy matching (`laohu → tiger`,
  `niao → bird`, `xiongmao → panda` …); smart filters (taxonomy / region /
  habitat / size / protection level); HTML-escaped `<mark>` highlighting;
  per-user recent history; trending; order results gated by `order:view`
  to prevent search-based data leakage.
- **Clock-in / out:** Server-side biometric pipeline — computes face-match
  score from submitted artifact against `Enrollment.reference_hash` (strict
  mode, default ON); device policy binds `device_id` to enrollment; rate
  limit (3/5min); canonical-hash anti-replay computed *after* server
  verification; configurable face threshold (default 0.85).
- **Punch corrections:** Admin approve/reject workflow; approved corrections
  produce a `TimePunch` using the full tamper-evident signature scheme (not
  a predictable stub) so integrity guarantees extend to retroactive entries.
- **Enrollments:** Admin-only API to create/replace/deactivate biometric
  enrollment references and device bindings; history-preserving
  (only one active per user).
- **Risk / Fraud:** Risk flags with admin clearance workflow; thresholds
  block redemptions and debits until cleared.
- **Exports:** CSV export for orders / members / bookings; export metadata
  is actor-scoped (non-admin sees only own export jobs).
- **Versioning:** Snapshot and rollback for `member` / `order` entities.
- **Audit:** Append-only `audit_logs` enforced at the ORM level; PII-redacted
  metadata; every login, role/permission change, order transition, booking
  action, clock-in, correction, enrollment, and export audited.

Architecture: **Route → Service → Model**. No business logic in routes.
Object-level ownership, field-level masking, and record-level scope are
all enforced uniformly.

## Quick Start with Docker

The fastest way to run the project. Docker handles all dependencies; no local Python installation required.

### 1. Run the application server

```bash
docker build -t wildlifelens .
docker run --rm -p 5000:5000 \
  -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  wildlifelens
```

On startup the container automatically runs `seed.py`, which creates one demo user per role, then starts the server. Open http://localhost:5000 in your browser and log in with any of the credentials in the table below.

### 2. Run the test suite (Docker)

```bash
bash run_tests.sh
```

This builds a clean test image, runs the full pytest suite, then performs an RBAC smoke-check that seeds the database and verifies `/api/auth/me` returns the correct role for every demo user. Use `--no-build` to skip the image rebuild.

---

## Demo Credentials

These users are created by `seed.py` and are available immediately after running the Docker container or after running `python seed.py` locally.

| Username        | Password       | Role          | Access level |
|-----------------|----------------|---------------|---|
| `admin`         | `Admin1234!`   | admin         | Full access — users, permissions, enrollments, corrections, all exports |
| `staff`         | `Staff1234!`   | staff         | Members, orders, bookings, exports (actor-scoped), search |
| `photographer`  | `Photo1234!`   | photographer  | Own bookings and schedules, search |
| `kitchen`       | `Kitchen1234!` | kitchen       | KDS read and ticket updates |
| `member`        | `Member1234!`  | member        | Own profile, points, orders |

### Verify authentication via API

```bash
# Log in and capture the session cookie
curl -s -c cookies.txt -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234!"}' | python -m json.tool

# Check current user and roles
curl -s -b cookies.txt http://localhost:5000/api/auth/me | python -m json.tool

# Confirm staff cannot access admin-only user list (expect 403)
curl -s -c cookies_staff.txt -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"staff","password":"Staff1234!"}' > /dev/null
curl -s -b cookies_staff.txt http://localhost:5000/api/users
```

### Seed manually (local / without Docker)

```bash
python seed.py
```

The script is idempotent — re-running it skips users that already exist.

---

## Run (local, without Docker)

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

# Required: set a secret key (app refuses to start with the default)
# Windows:
set SECRET_KEY=your-secret-key-here
# Linux / macOS:
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Seed demo users (optional but recommended for first run)
python seed.py

# Optional environment variables:
# ENCRYPTION_KEY            — override derived Fernet key (default: derived from SECRET_KEY)
# EXPORT_DIR                — CSV export directory (default: exports)
# FLASK_DEBUG               — "true" to enable Flask debug mode (default: false)
# DATABASE_URL              — SQLAlchemy URI (default: sqlite:///wildlifelens.db)
# CLOCKIN_FACE_THRESHOLD    — face-match threshold (default: 0.85)
# CLOCKIN_MIN_BRIGHTNESS    — minimum capture brightness (default: 0.5)
# CLOCKIN_STRICT            — "true" requires server-side artifact (default: true)

python wsgi.py
```

Server listens at http://127.0.0.1:5000.

### CLI

```bash
flask check-expiry   # run a single order-expiry sweep (cron-friendly)
```

A background `threading.Timer` also runs the sweep every 60 s inside the
Flask process (disabled under `TESTING`).

## Test

```bash
# Docker (recommended — no local dependencies needed):
bash run_tests.sh

# Local:
pytest
```

Test suites:

- `tests/test_auth/`         — authentication, session, role management, CSRF/content-type
- `tests/test_members/`      — member lookup/create, phone hash, tier benefits, field grants
- `tests/test_orders/`       — order API + state machine + ownership + receipt scope
- `tests/test_ui/`           — HTML/HTMX rendering, masked display
- `tests/test_e2e/`          — full flow: register → login → member → order → pay → advance
- `tests/test_bookings/`     — booking conflict, lock expiry, schedule-aware validation
- `tests/test_schedules/`    — photographer schedule CRUD
- `tests/test_kds/`          — KDS ticket routing, minutes-late alert
- `tests/test_search/`       — keyword, pinyin, synonyms, recent, trending, order-authz
- `tests/test_clockin/`      — pipeline, anti-replay, strict mode, face match,
                               corrections, enrollment API, device policy, config threshold
- `tests/test_risk/`         — risk flag management
- `tests/test_exports/`      — CSV export + actor-scoped listing
- `tests/test_versioning/`   — snapshot / rollback
- `tests/test_encryption/`   — encryption/decryption round-trip
- `tests/test_permissions/`  — RBAC + ABAC (field/record/cross-resource scope)
- `tests/test_points/`       — points earn/redeem/expiry + record-scope
- `tests/test_stored_value/` — stored-value ledger, masking, balance_after, record-scope
- `tests/test_tier_discount/`— tier discount caps
- `tests/test_expiry/`       — order auto-expiry (lazy + autonomous + single-4h window)

## Endpoints

### HTML (Jinja + HTMX, CSRF-protected)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| GET  | `/login` | Login page |
| POST | `/auth/login` | Login form handler (HTMX-aware) |
| POST | `/auth/logout` | Logout |
| GET  | `/members` | Member lookup page |
| GET  | `/members/lookup?q=` | HTMX partial — member card + tier benefits |
| GET  | `/orders/create` | Order creation page |
| POST | `/orders/create` | Form submit |
| GET  | `/orders/{id}` | Order detail + receipt + print button |
| POST | `/orders/{id}/pay` | HTMX partial — pay with optional `redeem_points` |
| POST | `/orders/{id}/advance` | HTMX partial — advance state |
| GET  | `/schedules` | Photographer schedule page with weekly calendar |
| POST | `/schedules/create` | Create schedule entry |
| GET  | `/bookings` | Booking management page |
| POST | `/bookings/create` | Create booking with lock |
| POST | `/bookings/{id}/confirm` | Confirm a locked booking |
| POST | `/bookings/{id}/cancel` | Cancel a booking |
| GET  | `/kds` | Kitchen display screen |
| GET  | `/search` | Search page with recent / trending suggestions |
| GET  | `/clock-in` | Clock-in kiosk page |
| POST | `/clock-in/submit` | Submit clock-in from kiosk |
| POST | `/clock-in/clock-out` | Submit clock-out from kiosk |
| POST | `/clock-in/correction` | Submit punch correction (requires `correction:submit`) |
| GET  | `/exports` | Export management page |
| POST | `/exports/create` | Create CSV export |
| GET  | `/risk` | Risk flag management page |
| POST | `/risk/{user_id}/clear` | Clear risk flags |
| GET  | `/versions` | Version snapshot management page |

### JSON API (session auth, `Content-Type: application/json` required on mutations)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| POST   | `/api/auth/register` | Register a user (default `member` role) |
| POST   | `/api/auth/login` | Login |
| POST   | `/api/auth/logout` | Logout |
| GET    | `/api/auth/me` | Current user |
| GET    | `/api/users` | List users (admin) |
| PUT    | `/api/users/{id}/roles` | Replace user's roles (admin) |
| POST   | `/api/users/{id}/roles` | Add single role (admin) |
| DELETE | `/api/users/{id}/roles/{role}` | Remove single role (admin) |
| POST   | `/api/members` | Create member |
| GET    | `/api/members/search?q=` | Lookup (exact, partial fallback, record-scoped) |
| GET    | `/api/members/{id}` | Member detail (masking + record-scope) |
| POST   | `/api/orders` | Create order (supports `items` for KDS routing) |
| GET    | `/api/orders/{id}` | Order detail (record-scope) |
| POST   | `/api/orders/{id}/pay` | Pay + optional `redeem_points` |
| POST   | `/api/orders/{id}/advance` | Advance state |
| GET    | `/api/orders/{id}/receipt` | JSON receipt |
| GET    | `/api/orders/{id}/receipt/print` | Plain-text printable receipt |
| POST   | `/api/schedules` | Create schedule |
| GET    | `/api/schedules` | List schedules |
| POST   | `/api/bookings` | Create booking (schedule-validated) |
| GET    | `/api/bookings` | List bookings (actor-scoped) |
| POST   | `/api/bookings/{id}/confirm` | Confirm (record-scope) |
| POST   | `/api/bookings/{id}/cancel` | Cancel (record-scope) |
| GET    | `/api/kds` | List KDS tickets |
| POST   | `/api/kds/{id}/start` | Start preparing |
| POST   | `/api/kds/{id}/complete` | Complete + write-back + auto-advance |
| GET    | `/api/search?q=` | Search members/orders/catalog (synonyms + pinyin) |
| GET    | `/api/search/recent` | Recent searches (per-user) |
| GET    | `/api/search/trending` | Trending terms (admin/staff) |
| POST   | `/api/clock-in` | Submit clock-in (strict: requires `face_image_hash`) |
| POST   | `/api/clock-out` | Submit clock-out |
| POST   | `/api/corrections` | Submit punch correction |
| GET    | `/api/corrections` | List corrections (admin=all, others=own) |
| POST   | `/api/corrections/{id}/approve` | Approve (admin) — creates signed punch |
| POST   | `/api/corrections/{id}/reject` | Reject (admin) |
| GET    | `/api/enrollments` | List enrollments (admin) |
| GET    | `/api/enrollments/{user_id}` | Get active enrollment (admin) |
| POST   | `/api/enrollments/{user_id}` | Create/replace enrollment (admin) |
| DELETE | `/api/enrollments/{user_id}` | Deactivate enrollment (admin) |
| GET    | `/api/risk` | List risk flags |
| POST   | `/api/risk/{user_id}/clear` | Clear risk flags for a user (admin) |
| POST   | `/api/risk/member/{member_id}/clear` | Clear risk flags for a member (admin) |
| POST   | `/api/exports` | Create export |
| GET    | `/api/exports` | List exports (actor-scoped) |
| POST   | `/api/points/redeem` | Redeem points (record-scope on member + order) |
| GET    | `/api/points/balance/{member_id}` | Balance |
| GET    | `/api/points/history/{member_id}` | History |
| POST   | `/api/stored-value/credit` | Credit (record-scope) |
| POST   | `/api/stored-value/debit` | Debit (record-scope + risk flag check) |
| GET    | `/api/stored-value/balance/{member_id}` | Balance (masked for non-admin) |
| GET    | `/api/stored-value/history/{member_id}` | History with `balance_after` |
| GET    | `/api/permissions` | List scope permissions (admin) |
| POST   | `/api/permissions` | Grant scope permission (admin) |
| DELETE | `/api/permissions/{id}` | Revoke (admin) |
| GET    | `/api/tiers` | List tier rules + benefits |
| GET    | `/api/tiers/{name}` | Single tier rule |
| POST   | `/api/versions/{type}/{id}/snapshot` | Create snapshot (admin) |
| POST   | `/api/versions/{type}/{id}/rollback` | Rollback (admin) |
| GET    | `/api/versions?entity_type=&entity_id=` | List snapshots (admin) |

## Order state machine

```
created → paid → in_prep → ready → delivered → reviewed
                              ↘ ready_for_pickup → delivered
```

- `created` auto-cancels after 30 minutes if unpaid.
- `ready` moves to `ready_for_pickup` after 4 hours unclaimed (single 4-hour
  deadline aligned with prompt semantics).
- `ready_for_pickup` cancels on the next expiry check — the short state is
  used as a reconciliation label for end-of-day reporting.

Invalid / duplicate / final-state transitions raise `InvalidTransitionError`
and return HTTP 400.

## Audit log

Every login, registration, role assignment, permission grant/revoke, member
CRUD, order transition, booking action, clock-in/out, correction
approve/reject, enrollment, risk-flag change, and version snapshot/rollback
is recorded in the append-only `audit_logs` table with actor, action,
resource, timestamp, and PII-redacted JSON metadata. `AuditLog` blocks
ORM-level `update` / `delete`.

## Security

- **CSRF:** Flask-WTF `CSRFProtect` for view/form routes. JSON APIs require
  `Content-Type: application/json` on every mutating call (including bodyless
  ones) — enforced at `before_request`, returns `415 Unsupported Media Type`
  otherwise.
- **Encryption:** PII (`phone_number`, `stored_value_balance`) encrypted with
  Fernet (AES-128-CBC); key derived from `SECRET_KEY` via PBKDF2.
- **Indexed phone hash:** HMAC-SHA256 of normalized digits for O(log n)
  lookup without decrypting every row.
- **RBAC + ABAC:** static role/action matrix plus admin-configurable
  `ScopePermission` grants (`location` / `station` / `employee` / `field` /
  `record` / `menu` / `api`).
- **Ownership & record-scope:** orders/bookings track `created_by`; record-scope
  enforced via `@permission_required(..., record_scope=True)` on receipt,
  view, pay, advance, confirm, cancel, and inside financial mutation bodies
  (points/redeem, stored-value/credit+debit).
- **Clock-in integrity:** server-side face match against enrollment hash,
  device policy, rate limiting, canonical-hash replay protection computed
  *after* server verification; same scheme applies to approved corrections.
- **Audit:** all security-relevant actions logged with PII-redacted metadata.

## Project layout

```
app/
  api/        # JSON endpoints (content-type-hardened, CSRF-exempt)
  views/      # HTMX/Jinja endpoints (CSRF-protected)
  services/   # Business logic (Route → Service → Model)
  models/     # SQLAlchemy models
  core/       # rbac, state_machine, encryption, security
  db/         # SQLAlchemy init
static/
  js/         # Vendored JS (htmx.min.js — no external CDN)
templates/
  base.html, login.html, members.html, order_create.html, order_detail.html,
  schedules.html, bookings.html, kds.html, search.html, clockin.html,
  exports.html, risk.html, versions.html
  partials/   # HTMX partial fragments
tests/
  test_auth/      test_members/   test_orders/    test_ui/        test_e2e/
  test_bookings/  test_schedules/ test_kds/       test_search/    test_clockin/
  test_risk/      test_exports/   test_versioning/ test_encryption/
  test_permissions/ test_points/  test_stored_value/ test_tier_discount/
  test_expiry/
```
