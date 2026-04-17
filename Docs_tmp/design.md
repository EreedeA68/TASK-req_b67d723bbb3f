# Design Document — WildLifeLens Operations Suite

## 1. Overview

WildLifeLens Operations Suite is a fully offline-capable, single-server Flask application providing an end-to-end operations platform for a wildlife photography studio. It covers member management, order lifecycle, kitchen display, photographer scheduling and booking, staff clock-in, risk controls, exports, and admin governance — all running without a network dependency on any external service.

The system targets kiosk terminals and front-counter workstations. The browser communicates with the server over a local LAN; HTMX drives all UI interactions with server-rendered HTML partials; a JSON API supports machine-to-machine and integration use cases.

---

## 2. Architecture

### 2.1 Layer Model

```
Browser (HTMX + Jinja2)
        │  HTTP (local LAN)
        ▼
Flask Application
  ├── app/views/       — HTML/HTMX routes (CSRF-protected, Jinja2)
  ├── app/api/         — JSON API routes (Content-Type enforced)
  │         │
  │         ▼
  ├── app/services/    — Business logic (no SQLAlchemy in routes)
  │         │
  │         ▼
  ├── app/models/      — SQLAlchemy ORM models
  └── app/core/        — Cross-cutting: RBAC, state machine, encryption, security
        │
        ▼
SQLite (file or :memory: for tests)
```

All business logic lives in `services/`. Routes are thin: they parse the request, call a service function, and serialize the response. This keeps routes testable and replaceable.

### 2.2 Request Flow

1. Flask processes the request through `before_request` middleware which enforces `Content-Type: application/json` on all mutating JSON API calls.
2. The `@permission_required(resource, action)` decorator verifies RBAC (and optionally ABAC record-scope) before the view function runs.
3. The view/API calls the appropriate service function.
4. The service interacts with SQLAlchemy models and commits the session.
5. For auditable actions, `audit_service.log(...)` is called before the response is returned.

---

## 3. Authentication & Authorization

### 3.1 Authentication

Session-based using Flask's signed cookie sessions. Passwords are hashed with bcrypt (work factor 12). The `init_app` hook in `Config` fails fast at startup if `SECRET_KEY` is the insecure default, preventing accidental production deployments.

Session cookies are configured with `HttpOnly=True`, `Secure=True` (overridden to `False` in `TestConfig`), and `SameSite=Lax`.

### 3.2 RBAC — Static Role Matrix

Five roles: `admin`, `staff`, `photographer`, `kitchen`, `member`. Each role has a fixed set of `(resource, action)` pairs defined in `app/core/rbac.py`. The `@permission_required` decorator checks this matrix on every protected route.

```
admin        — full access to all resources
staff        — member/order/booking/search/export operations
photographer — own booking/schedule view; search
kitchen      — KDS read/update
member       — own profile/points/orders
```

### 3.3 ABAC — Dynamic Scope Grants

Admins can create `ScopePermission` records granting additional access beyond the static matrix. Seven scope types:

| Scope type | Effect |
|---|---|
| `location`  | Limits access to resources at a given location |
| `station`   | Limits KDS/order access to a named station |
| `employee`  | Limits access to a specific employee's records |
| `field`     | Unmasks a specific PII field (e.g. `phone_number`) for a role |
| `record`    | Grants access to a specific record ID |
| `menu`      | Limits catalog/item visibility to a menu section |
| `api`       | Grants access to a specific API path |

The `@permission_required(..., record_scope=True)` decorator calls `permission_service.check_record_access` for object-level enforcement. Financial mutation endpoints (`points/redeem`, `stored-value/credit+debit`) perform field-level and record-level checks internally.

---

## 4. Data Model

### 4.1 Core Entities

**User** — `users` table. Username + bcrypt hash. Many-to-many with `Role` via `user_roles`.

**Member** — `members` table. `name`, `member_id` (unique business key), encrypted `phone_number` (Fernet), HMAC-SHA256 `phone_hash` (indexed for O(log n) lookup without full decryption scan), encrypted `stored_value_balance`, `tier`, `points_balance`.

**Order** — `orders` table. State machine column `status`. `created_by` FK to `users`. Linked to `OrderEvent` records (immutable audit trail of status transitions) and `KDSTicket` records.

**Booking** — `bookings` table. `member_id`, `photographer_id`, `created_by`, `start_time`, `end_time`, `status` (`locked`/`confirmed`/`cancelled`), `lock_expires_at`.

**Schedule** — `schedules` table. `photographer_id`, `date`, `start_time`, `end_time`, `type` (`working`/`break`/`off`).

**KDSTicket** — `kds_tickets` table. Linked to `Order`. Carries `station`, `items` (JSON), `status`, `allergy_flags`.

**SearchLog** / **SearchTrend** — `search_logs` / `search_trends` tables. `SearchLog` carries `term`, `user_id`, `device_id` for per-device history isolation. `SearchTrend` aggregates global counts by term.

**AuditLog** — `audit_logs` table. Append-only; ORM `before_update` / `before_delete` events raise `RuntimeError` if modification is attempted at the ORM level.

**ExportJob** — `export_jobs` table. Tracks CSV generation jobs by actor.

**TimePunch** / **PunchCorrection** — clock-in/out records with tamper-evident HMAC-SHA256 signature.

**Enrollment** — biometric enrollment references. One active per user; deactivation is soft (history-preserving).

**RiskFlag** — `risk_flags` table. Blocks redemptions and stored-value debits until admin clearance.

**VersionSnapshot** — `version_snapshots` table. JSON blob of entity state at snapshot time.

### 4.2 Encryption

PII fields (`phone_number`, `stored_value_balance`) are encrypted with Fernet (AES-128-CBC + HMAC-SHA256). The key is derived from `SECRET_KEY` via PBKDF2 (100,000 rounds, SHA-256, 32-byte output) using a fixed application salt. This makes the key deterministic across restarts while still being derived, not stored in plaintext.

A separate `phone_hash` column stores the HMAC-SHA256 of the normalized phone number. This enables O(log n) exact-phone lookups without decrypting every row; partial/fuzzy phone matches require a full decryption scan but are bounded by `LIMIT 50`.

---

## 5. Order State Machine

```
created ──(pay)──► paid ──(advance)──► in_prep ──(advance)──► ready
                                                                  │
                                                    (advance) ◄───┤
                                                         │         └──► ready_for_pickup
                                                         ▼                    │
                                                     delivered ◄──────────────┘
                                                         │
                                                    (advance)
                                                         ▼
                                                      reviewed
```

- `created` auto-expires after 30 minutes (background ticker + `flask check-expiry` CLI).
- `ready` transitions to `ready_for_pickup` after 4 hours unclaimed.
- `ready_for_pickup` is cancelled on the next expiry sweep; used as a reconciliation label.
- Invalid, duplicate, and final-state transitions raise `InvalidTransitionError` → HTTP 400.

The state machine is implemented as a pure-function transition table in `app/core/state_machine.py`. Services call `state_machine.transition(order, new_status)` and then persist via SQLAlchemy.

---

## 6. KDS (Kitchen Display System)

When an order is created with an `items` list, `kds_service.create_tickets` derives the station for each item from its `category`:

| Category   | Station  |
|---|---|
| drink      | bar      |
| grill      | grill    |
| dessert    | pastry   |
| (default)  | kitchen  |

One ticket is created per station (items for the same station are grouped). Allergy flags on any item propagate to the ticket. The `minutes_late` field is computed at query time from `created_at` vs. a configurable target time.

When all tickets for an order reach `done`, `kds_service.complete_ticket` triggers an order write-back event and auto-advances the order to `ready`.

---

## 7. Search

`search_service.perform_search` runs across three corpora:

1. **Members** — LIKE matching against `name` and `member_id` (plaintext columns); decryption scan of `phone_number` for phone queries.
2. **Orders** — ID and status matching, gated by `order:view` permission.
3. **Catalog items** — LIKE matching against `name`, `category`, `taxonomy`, `region`, `habitat`, `size_range`, `protection_level`.

**Synonym expansion** — a static dictionary maps common shorthand terms and pinyin transliterations to English equivalents (e.g. `laohu → tiger`, `xiongmao → panda`, `niao → bird`). The search query is expanded before building the LIKE clause, so searches in either language match the same records.

**HTML highlighting** — matched fragments in member names are wrapped in `<mark>` tags using a regex substitution on the HTML-escaped result string.

**Device-local recency** — when the client sends `X-Device-ID` (set automatically by the HTMX `configRequest` hook in `base.html`), search queries are recorded with that device ID. `get_recent` and `get_trending` filter by `device_id` when present, isolating terminal-specific suggestions from shared-account contexts.

**PII in search logs** — digit-only queries of ≥7 characters (phone-like) are hashed via SHA-256 before storage; the raw number is never written to `search_logs`.

---

## 8. Clock-In Pipeline

1. Client submits `user_id`, `device_id`, `face_image_hash`, `brightness`.
2. `clockin_service` checks the rate limit (3 punches per 5 minutes per user).
3. Brightness is validated against `CLOCKIN_MIN_BRIGHTNESS` (default 0.5).
4. In strict mode (`CLOCKIN_STRICT=true`, production default), `face_image_hash` is required.
5. The service looks up the active `Enrollment` for `(user_id, device_id)`, computes a face-match score against `reference_hash`, and rejects if below `CLOCKIN_FACE_THRESHOLD` (default 0.85).
6. A canonical replay hash is computed server-side after verification. Any repeat submission of the same canonical hash is rejected.
7. A `TimePunch` is recorded with a tamper-evident HMAC-SHA256 signature derived from `(user_id, device_id, punched_at, SECRET_KEY)`.
8. The punch ID, signature, and timestamp are returned to the client.

Punch corrections follow the same signature scheme once approved by an admin, so retroactive entries carry the same integrity guarantees as real-time punches.

---

## 9. Security Controls Summary

| Control | Implementation |
|---|---|
| Password storage | bcrypt, work factor 12 |
| Session cookie | HttpOnly + Secure + SameSite=Lax |
| CSRF (views) | Flask-WTF CSRFProtect; token in `<meta>` tag, injected via HTMX configRequest |
| CSRF (JSON API) | `Content-Type: application/json` required on all mutations; enforced in `before_request` |
| PII encryption | Fernet / AES-128-CBC, key derived via PBKDF2 |
| PII masking | `mask_phone` / `mask_balance` applied to non-admin responses |
| RBAC | Static `(role, resource, action)` matrix in `rbac.py` |
| ABAC | `ScopePermission` records, enforced via decorator + service checks |
| Record-level authz | `check_record_access` in `permission_service` |
| Export scope | Non-admin CSV rows filtered to actor-linked records |
| Audit trail | Append-only `audit_logs`; ORM hooks block update/delete |
| Risk flags | Block redemption/debit until admin clearance |
| Clock-in integrity | Face match, device binding, rate limit, anti-replay, HMAC signatures |
| Secret key guard | `init_app` raises `RuntimeError` if default key is used in non-test env |

---

## 10. Offline-First Design

The application has zero external network dependencies at runtime:

- SQLite for persistence (file-based, bundled with Python).
- Fernet keys derived locally from `SECRET_KEY`.
- HTMX vendored locally at `static/js/htmx.min.js` (no CDN).
- No background queues, no external auth providers, no remote logging.

The only external tooling is Python itself and pip for the initial install. Once the venv is built, the application runs fully offline.

---

## 11. Testing Strategy

Tests use `pytest` with `pytest-flask`. The `TestConfig` uses an in-memory SQLite database (`:memory:`), so each test gets a fresh schema. Export files are routed to pytest's `tmp_path` fixture so they are automatically cleaned up. `sys.dont_write_bytecode = True` is set in `conftest.py` and a session-scoped fixture purges `__pycache__` directories after each run.

The test suite covers:

- **Unit tests** — individual service functions with direct DB assertions.
- **API/integration tests** — Flask test client hitting full route→service→model stacks.
- **E2E tests** — multi-step flows (register → login → create member → create order → pay → advance → export).
- **Security tests** — unauthorized access (401/403), CSRF rejection (415), scope isolation, record-scope enforcement, export data-scope regression.

Docker-based test execution is provided via `Dockerfile.test` and `run_tests.sh` so CI environments require no local Python installation.
