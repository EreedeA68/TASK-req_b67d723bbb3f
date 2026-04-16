# Delivery Acceptance and Project Architecture Audit (Static-Only)

## 1. Verdict
- Overall conclusion: **Partial Pass**

## 2. Scope and Static Verification Boundary
- Reviewed:
  - Repository structure, startup/config/test docs: `repo/README.md:1`, `Docs/design.md:1`, `Docs/api-spec.md:1`, `repo/config.py:1`, `repo/wsgi.py:1`
  - App bootstrap, authn/authz, RBAC/ABAC, core services/models, API + view routes
  - Test suite inventory and representative coverage across auth, permissions, members, orders, bookings, schedules, search, clock-in, risk, exports, versioning
- Not reviewed:
  - Runtime behavior in a live environment, browser rendering fidelity under real devices, OS print integration, long-running timer behavior under process restarts
- Intentionally not executed:
  - Project startup, Docker, test runs, external integrations (per instructions)
- Manual verification required for:
  - Real-time UX behavior under concurrent staff usage
  - Kiosk hardware/browser behavior for printing and camera artifact capture flow
  - Performance characteristics (search responsiveness, DB size scaling)

## 3. Repository / Requirement Mapping Summary
- Prompt core goal mapped: offline Flask+SQLite+HTMX operations suite spanning member lookup, tier/points/stored-value, order lifecycle + KDS, scheduling/booking, search, clock-in validation, risk flags, exports, and audit trail.
- Main implementation areas mapped:
  - API/view entry points and wiring: `repo/app/__init__.py:40`
  - Security and permission layers: `repo/app/core/rbac.py:8`, `repo/app/services/permission_service.py:73`
  - Core business services: orders, bookings, schedules, KDS, search, points, stored value, clock-in, risk
  - Static tests and fixtures: `repo/tests/conftest.py:19`, `repo/pytest.ini:1`

## 4. Section-by-section Review

### 4.1 Hard Gate 1.1 Documentation and static verifiability
- Conclusion: **Pass**
- Rationale: Startup/test/config instructions and endpoint inventory are present and statically consistent with app registration and config enforcement.
- Evidence:
  - Run/test/config docs: `repo/README.md:61`, `repo/README.md:98`
  - App factory and blueprint registration: `repo/app/__init__.py:40`
  - Secret-key fail-fast: `repo/config.py:40`

### 4.2 Hard Gate 1.2 Material deviation from Prompt
- Conclusion: **Partial Pass**
- Rationale: Most major flows exist, but there is a significant mismatch in kiosk clock-in under default strict mode and a risk-policy mismatch for redemption blocking.
- Evidence:
  - Strict mode default ON: `repo/config.py:61`
  - Strict mode requires artifact: `repo/app/services/clockin_service.py:221`
  - Kiosk form/view does not submit `face_image_hash`: `repo/templates/clockin.html:10`, `repo/app/views/clockin.py:25`
  - Spend-abuse flag raised in stored value path: `repo/app/services/stored_value_service.py:169`
  - Points redemption blocks only `points_abuse`: `repo/app/services/points_service.py:93`
- Manual verification note: Runtime kiosk camera-artifact capture flow is required to confirm intended production behavior.

### 4.3 Delivery Completeness 2.1 Core explicit requirements coverage
- Conclusion: **Partial Pass**
- Rationale: Core modules are implemented (members/orders/KDS/bookings/search/clock-in/risk/exports), but two prompt-critical behaviors are not fully aligned (strict kiosk submission path, redemption blocking semantics).
- Evidence:
  - Core modules present: `repo/app/services/order_service.py:61`, `repo/app/services/booking_service.py:136`, `repo/app/services/search_service.py:135`, `repo/app/services/clockin_service.py:144`
  - Gaps: `repo/config.py:61`, `repo/app/views/clockin.py:25`, `repo/app/services/points_service.py:93`

### 4.4 Delivery Completeness 2.2 End-to-end 0-to-1 deliverable
- Conclusion: **Pass**
- Rationale: Complete multi-module app with docs, routes, templates, models, services, and extensive tests; not a code fragment/demo.
- Evidence:
  - Project layout/documentation: `repo/README.md:271`
  - E2E tests exist: `repo/tests/test_e2e/test_e2e.py:9`, `repo/tests/test_e2e/test_e2e_phase2.py:5`, `repo/tests/test_e2e/test_e2e_phase3.py:5`

### 4.5 Engineering and Architecture Quality 3.1 Structure and decomposition
- Conclusion: **Pass**
- Rationale: Clear route→service→model separation with blueprint/module decomposition and dedicated core/security layers.
- Evidence:
  - Stated and reflected layering: `repo/README.md:57`, `repo/app/__init__.py:40`
  - Service-focused business logic: `repo/app/services/order_service.py:1`, `repo/app/services/booking_service.py:1`

### 4.6 Engineering and Architecture Quality 3.2 Maintainability/extensibility
- Conclusion: **Partial Pass**
- Rationale: Overall maintainable, but authorization behavior diverges between API and view layers (record-scope ABAC bypass risk), indicating policy enforcement duplication drift.
- Evidence:
  - API routes enforce record_scope: `repo/app/api/orders.py:41`, `repo/app/api/bookings.py:50`
  - Equivalent view routes omit record_scope: `repo/app/views/orders.py:112`, `repo/app/views/bookings.py:73`
  - Staff broad object access in view-side checks: `repo/app/services/order_service.py:42`, `repo/app/services/booking_service.py:39`

### 4.7 Engineering Details and Professionalism 4.1 Error handling/logging/validation/API design
- Conclusion: **Partial Pass**
- Rationale: Strong validation/audit coverage overall, but critical authorization and policy mismatches remain.
- Evidence:
  - Validation and errors: `repo/app/api/orders.py:17`, `repo/app/services/order_service.py:49`
  - Central audit logging: `repo/app/services/audit_service.py:6`
  - Authorization mismatch examples: `repo/app/views/orders.py:130`, `repo/app/views/bookings.py:92`

### 4.8 Engineering Details and Professionalism 4.2 Product-like vs demo-like
- Conclusion: **Pass**
- Rationale: Breadth of modules, persistent models, role/permission surface, and static test depth are product-oriented.
- Evidence:
  - Feature breadth in code/docs: `repo/README.md:3`, `Docs/design.md:248`

### 4.9 Prompt Understanding and Requirement Fit 5.1 Semantics and constraints fit
- Conclusion: **Partial Pass**
- Rationale: Broadly aligned, but the strict-mode kiosk path and redemption-blocking semantics materially weaken prompt fit.
- Evidence:
  - Prompt-fit modules: `repo/app/services/expiry_service.py:9`, `repo/app/services/kds_service.py:25`, `repo/app/services/search_service.py:135`
  - Mismatches: `repo/config.py:61`, `repo/app/views/clockin.py:25`, `repo/app/services/points_service.py:93`

### 4.10 Aesthetics 6.1 Visual/interaction quality
- Conclusion: **Partial Pass**
- Rationale: Functional and consistent HTMX UI with feedback states exists, but design is very minimal and does not strongly demonstrate scenario-tailored visual hierarchy quality.
- Evidence:
  - Base styling is minimal: `repo/templates/base.html:9`
  - Interaction feedback present (HTMX partials/countdowns/alerts): `repo/templates/partials/order_status.html:8`, `repo/templates/partials/kds_ticket_row.html:8`
- Manual verification note: Browser/device rendering polish still requires human walkthrough.

## 5. Issues / Suggestions (Severity-Rated)

### 5.1 High — Record-scope ABAC can be bypassed via view endpoints
- Conclusion: **Fail**
- Evidence:
  - API enforces record scope for orders/bookings: `repo/app/api/orders.py:41`, `repo/app/api/bookings.py:50`
  - Corresponding view routes do not: `repo/app/views/orders.py:112`, `repo/app/views/orders.py:130`, `repo/app/views/orders.py:162`, `repo/app/views/bookings.py:73`, `repo/app/views/bookings.py:93`
  - View-side object checks allow staff broad access: `repo/app/services/order_service.py:42`, `repo/app/services/booking_service.py:39`
- Impact:
  - Admin-configured record-level ABAC restrictions can be bypassed by using HTML/HTMX routes, undermining data-scope enforcement and least privilege.
- Minimum actionable fix:
  - Apply `record_scope=True` on affected view decorators (or centralize all record checks in a shared enforcement function used by both API and view routes).

### 5.2 High — Default strict clock-in mode conflicts with kiosk view payload
- Conclusion: **Fail**
- Evidence:
  - Strict default enabled: `repo/config.py:61`
  - Strict mode requires `face_image_hash`: `repo/app/services/clockin_service.py:221`
  - Kiosk form/view submits only claimed score/brightness/face_count/device_id: `repo/templates/clockin.html:10`, `repo/app/views/clockin.py:25`
- Impact:
  - In default production configuration, kiosk clock-in through the documented HTMX view path is likely rejected (`artifact_required`), breaking a core staff workflow.
- Minimum actionable fix:
  - Add artifact capture/hash input flow in kiosk view and pass `face_image_hash` to service, or revise strict-mode defaults/documented operational path consistently.

### 5.3 High — Spend-abuse risk flag does not block points redemption path
- Conclusion: **Fail**
- Evidence:
  - Spend-abuse flag creation on >$200 stored-value debit: `repo/app/services/stored_value_service.py:169`
  - Points redeem checks only `points_abuse`: `repo/app/services/points_service.py:93`
- Impact:
  - Prompt states high-risk behavior should block further redemptions until admin clear; current implementation permits redemptions when only `spend_abuse` is active.
- Minimum actionable fix:
  - In points redemption guard, treat active `spend_abuse` (or any active risk flag) as blocking condition, per prompt policy.

### 5.4 Medium — Member record-scope filtering is not applied in order creation member picker
- Conclusion: **Partial Fail**
- Evidence:
  - Order create page loads first 200 members directly: `repo/app/views/orders.py:33`
  - No `check_record_access` filter applied in picker serialization path: `repo/app/views/orders.py:10`
- Impact:
  - Staff may see out-of-scope member identities in UI dropdown despite record-scope policy intent.
- Minimum actionable fix:
  - Filter picker members with `permission_service.check_record_access(actor, "member", "view", member.id)` before rendering.

### 5.5 Medium — Risk-clear API documentation omits member-clear path used by core risk flow
- Conclusion: **Partial Fail (Docs Consistency)**
- Evidence:
  - Member clear endpoint exists: `repo/app/api/risk.py:25`
  - README endpoint table lists only user clear path: `repo/README.md:204`
- Impact:
  - Static verification and operations runbooks may miss the required member-flag clearance endpoint.
- Minimum actionable fix:
  - Document `/api/risk/member/{member_id}/clear` consistently in README and API spec.

## 6. Security Review Summary

### 6.1 Authentication entry points
- Conclusion: **Pass**
- Evidence: `repo/app/api/auth.py:11`, `repo/app/services/auth_service.py:44`, `repo/app/core/security.py:5`
- Rationale: Session auth with password hashing and explicit login_required usage is implemented.

### 6.2 Route-level authorization
- Conclusion: **Partial Pass**
- Evidence: `repo/app/core/rbac.py:208`, `repo/app/api/orders.py:41`, `repo/app/views/orders.py:112`
- Rationale: Decorator coverage is broad, but inconsistent `record_scope` use between API and view routes creates exploitable policy gaps.

### 6.3 Object-level authorization
- Conclusion: **Partial Pass**
- Evidence: `repo/app/services/order_service.py:23`, `repo/app/services/booking_service.py:21`
- Rationale: Object checks exist, but operational-role broad allowances combined with missing view record-scope checks weaken enforced boundaries.

### 6.4 Function-level authorization
- Conclusion: **Pass**
- Evidence: Admin-only sensitive endpoints use permission checks (`repo/app/api/users.py:19`, `repo/app/api/permissions.py:19`, `repo/app/api/enrollments.py:28`).

### 6.5 Tenant / user data isolation
- Conclusion: **Partial Pass**
- Evidence: actor-scoped exports/bookings/recent searches (`repo/app/services/export_service.py:107`, `repo/app/services/booking_service.py:287`, `repo/app/services/search_service.py:320`), but order/member view-layer scope gaps (`repo/app/views/orders.py:112`, `repo/app/views/orders.py:33`).

### 6.6 Admin / internal / debug protection
- Conclusion: **Pass**
- Evidence: admin protections on users/permissions/versioning/enrollments/risk-clear (`repo/app/api/users.py:19`, `repo/app/api/permissions.py:19`, `repo/app/api/versions.py:23`, `repo/app/api/risk.py:18`).

## 7. Tests and Logging Review

### 7.1 Unit tests
- Conclusion: **Pass**
- Evidence: substantial service/model unit coverage across orders, permissions, risk, points, stored value, encryption, clock-in (`repo/tests/test_orders/test_orders.py:13`, `repo/tests/test_permissions/test_permissions.py:4`, `repo/tests/test_encryption/test_encryption.py:4`).

### 7.2 API / integration tests
- Conclusion: **Pass**
- Evidence: API/authz/error-path and e2e-style tests present (`repo/tests/test_auth/test_auth.py:9`, `repo/tests/test_permissions/test_abac_endpoint_integration.py:12`, `repo/tests/test_e2e/test_e2e.py:9`).

### 7.3 Logging categories / observability
- Conclusion: **Partial Pass**
- Evidence: central audit log actions are broad (`repo/app/services/audit_service.py:6`, `repo/app/models/audit.py:42`, `repo/tests/test_e2e/test_e2e.py:188`).
- Rationale: Security/business events are audited; however, there is minimal non-audit operational logging (runtime diagnostics mostly absent).

### 7.4 Sensitive-data leakage risk in logs / responses
- Conclusion: **Partial Pass**
- Evidence:
  - Masking/encryption paths: `repo/app/services/member_service.py:147`, `repo/app/core/encryption.py:28`
  - Search term redaction: `repo/app/services/search_service.py:289`
  - Export metadata exposes file paths by design to authorized roles: `repo/app/services/export_service.py:60`
- Rationale: Core PII handling is good; residual exposure risk remains around metadata/path disclosure for authorized users (acceptable but operationally sensitive).

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview
- Unit + API/integration tests exist: **Yes** (`repo/pytest.ini:1`, `repo/tests/conftest.py:19`)
- Framework: **pytest** (`repo/pytest.ini:1`)
- Test entry point: `pytest` documented (`repo/README.md:98`)
- Documentation provides test command: **Yes** (`repo/README.md:100`)

### 8.2 Coverage Mapping Table

| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Auth + session lifecycle | `repo/tests/test_auth/test_auth.py:49`, `repo/tests/test_auth/test_auth.py:104` | login success and post-logout denial assertions (`repo/tests/test_auth/test_auth.py:55`, `repo/tests/test_auth/test_auth.py:115`) | sufficient | None material | N/A |
| CSRF/content-type hardening incl bodyless mutations | `repo/tests/test_auth/test_csrf_content_type.py:4`, `repo/tests/test_auth/test_bodyless_csrf.py:8` | 415 checks for form/multipart/bodyless calls (`repo/tests/test_auth/test_bodyless_csrf.py:11`) | sufficient | None material | N/A |
| RBAC/ABAC API enforcement (field/record scope) | `repo/tests/test_permissions/test_abac_endpoint_integration.py:12`, `repo/tests/test_permissions/test_cross_resource_record_scope.py:12` | 403 for out-of-scope record and masked fields (`repo/tests/test_permissions/test_abac_endpoint_integration.py:51`) | basically covered | View-layer ABAC bypass not tested | Add tests for `/orders/{id}`, `/orders/{id}/pay`, `/bookings/{id}/confirm` via view routes under restrictive record scope |
| Order lifecycle + transition validation | `repo/tests/test_orders/test_orders.py:126`, `repo/tests/test_orders/test_orders.py:213` | status progression and invalid transition rejection (`repo/tests/test_orders/test_orders.py:233`) | sufficient | None material | N/A |
| Unpaid/pickup expiry windows | `repo/tests/test_expiry/test_expiry.py:18`, `repo/tests/test_expiry/test_pickup_expiry_window.py:24` | 30-min cancel and single-4h semantics checks (`repo/tests/test_expiry/test_expiry.py:36`, `repo/tests/test_expiry/test_pickup_expiry_window.py:45`) | sufficient | None material | N/A |
| KDS routing + late/allergy alerts + completion writeback | `repo/tests/test_kds/test_kds_routing.py:18`, `repo/tests/test_kds/test_late_alert.py:7` | station mapping/asserted events and “late by N min” assertions (`repo/tests/test_kds/test_kds_routing.py:101`, `repo/tests/test_kds/test_late_alert.py:29`) | sufficient | None material | N/A |
| Search synonym/pinyin + smart filters + order authz | `repo/tests/test_search/test_pinyin_search.py:27`, `repo/tests/test_search/test_catalog_search.py:96`, `repo/tests/test_search/test_search_order_authz.py:12` | pinyin expansion, filter assertions, and photographer order-visibility denial (`repo/tests/test_search/test_search_order_authz.py:29`) | sufficient | None material | N/A |
| Clock-in strict mode + server match + anti-replay | `repo/tests/test_clockin/test_strict_mode.py:19`, `repo/tests/test_clockin/test_server_face_match.py:53`, `repo/tests/test_clockin/test_antireplay.py:34` | strict artifact-required and duplicate-submission assertions (`repo/tests/test_clockin/test_strict_mode.py:31`, `repo/tests/test_clockin/test_antireplay.py:45`) | basically covered | Strict-mode **view** path not tested | Add view test with `CLOCKIN_STRICT=True` for `/clock-in/submit` expecting success with artifact or explicit rejection UX contract |
| Points/stored-value policy + risk interaction | `repo/tests/test_points/test_points.py:76`, `repo/tests/test_stored_value/test_stored_value.py:75` | 20% cap, >$200 spend flag creation (`repo/tests/test_points/test_points.py:94`, `repo/tests/test_stored_value/test_stored_value.py:91`) | insufficient | No test that `spend_abuse` blocks points redemption | Add test: flag `spend_abuse` then assert `/api/points/redeem` blocked |
| Export metadata isolation | `repo/tests/test_exports/test_export_scope.py:12` | non-admin only sees own exports (`repo/tests/test_exports/test_export_scope.py:35`) | sufficient | None material | N/A |

### 8.3 Security Coverage Audit
- authentication: **Pass**
  - Covered by login/logout/me tests and failed-login audit assertions (`repo/tests/test_auth/test_auth.py:49`, `repo/tests/test_auth/test_auth.py:61`).
- route authorization: **Partial Pass**
  - API authz paths covered (`repo/tests/test_permissions/test_cross_resource_record_scope.py:12`), but view-route ABAC parity is not tested.
- object-level authorization: **Partial Pass**
  - Order cross-user API access tested (`repo/tests/test_orders/test_cross_user_access.py:24`), view endpoint bypass scenarios missing.
- tenant/data isolation: **Partial Pass**
  - Export and recent-search scoping tested (`repo/tests/test_exports/test_export_scope.py:12`, `repo/tests/test_search/test_recent_trending.py:19`), but member picker/view-level scope leakage not covered.
- admin/internal protection: **Pass**
  - Non-admin denial and admin-only tests for users/permissions/enrollments/risk clear exist (`repo/tests/test_auth/test_user_roles.py:12`, `repo/tests/test_permissions/test_permissions.py:136`, `repo/tests/test_clockin/test_enrollment_api.py:12`, `repo/tests/test_risk/test_risk.py:74`).

### 8.4 Final Coverage Judgment
- **Partial Pass**
- Covered major risks:
  - Auth/session, CSRF/content-type hardening, core order lifecycle, expiry, KDS routing/alerts, search authz/filters, core clock-in anti-replay.
- Uncovered risks allowing severe defects to slip while tests still pass:
  - View-layer record-scope ABAC bypass (orders/bookings/member picker)
  - Strict-mode kiosk view incompatibility
  - Missing policy test for spend-abuse blocking redemption behavior

## 9. Final Notes
- Audit conclusions are static-only and evidence-bound to repository files.
- The most material acceptance risks are authorization consistency across UI/API and strict clock-in workflow alignment with default production configuration.
