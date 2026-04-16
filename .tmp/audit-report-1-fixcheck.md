# Follow-Up Review of Previously Reported Issues

Date: 2026-04-16

## Scope and Boundary

- Reviewed previously reported issues from `.tmp/delivery-acceptance-architecture-audit-static-20260416-codex.md`.
- Static analysis only.
- Did not start the project, run tests, run Docker, or perform browser/manual checks.
- Conclusions are limited to what is provable from current repository contents.

## Summary

- Fixed: 5
- Partially Fixed: 0
- Not Fixed: 0

## Issue-by-Issue Verification

### 1. Record-scope ABAC can be bypassed via view endpoints
- Status: `Fixed`
- Rationale: The affected order and booking HTMX/view routes now enforce record-level scope at the decorator level, aligning view enforcement with API enforcement.
- Evidence:
  - `repo/app/views/orders.py:121`
  - `repo/app/views/orders.py:140`
  - `repo/app/views/orders.py:172`
  - `repo/app/views/bookings.py:73`
  - `repo/app/views/bookings.py:93`

### 2. Default strict clock-in mode conflicts with kiosk view payload
- Status: `Fixed`
- Rationale: Strict mode remains enabled by default, but the kiosk flow now submits `face_image_hash`; the view passes it through and the service strict guard consumes it.
- Evidence:
  - `repo/config.py:61`
  - `repo/templates/clockin.html:14`
  - `repo/templates/clockin.html:41`
  - `repo/app/views/clockin.py:27`
  - `repo/app/views/clockin.py:37`
  - `repo/app/services/clockin_service.py:221`

### 3. Spend-abuse risk flag does not block points redemption path
- Status: `Fixed`
- Rationale: Points redemption now blocks when either `points_abuse` or `spend_abuse` is active, closing the prior guard gap.
- Evidence:
  - `repo/app/services/points_service.py:95`
  - `repo/app/services/points_service.py:96`
  - `repo/app/services/stored_value_service.py:169`
  - `repo/app/services/stored_value_service.py:171`

### 4. Member record-scope filtering is not applied in order creation member picker
- Status: `Fixed`
- Rationale: The member picker path now filters candidates through record-access checks before rendering.
- Evidence:
  - `repo/app/views/orders.py:22`

### 5. Risk-clear API documentation omits member-clear path used by core risk flow
- Status: `Fixed`
- Rationale: README endpoint table now documents the member clear API route.
- Evidence:
  - `repo/app/api/risk.py:25`
  - `repo/README.md:206`

## Final Assessment

All previously reported issues in `.tmp/delivery-acceptance-architecture-audit-static-20260416-codex.md` are now addressed by static code/documentation evidence.

Static boundary still applies:

- This recheck did not execute the project or tests.
- Runtime integration behavior remains manual verification scope in general.
