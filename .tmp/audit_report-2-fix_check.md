# Follow-Up Review of Previously Reported Issues (Consolidated Recheck)

Date: 2026-04-17

## Scope and Boundary

- Reviewed all previously reported issues from `.tmp/delivery-acceptance-architecture-audit-static-20260416-codex-v2.md`.
- Static analysis only.
- Did not start the project, run tests, run Docker, or perform browser/manual checks.
- Conclusions below are limited to what is provable from current repository contents.

## Summary

- Fixed: 6
- Partially Fixed: 0
- Not Fixed: 0

## Issue-by-Issue Verification

### 1. Export endpoints bypass record/data scope and allow broad dataset extraction by staff
- Status: `Fixed`
- Rationale: Non-admin export scope now applies to `orders`, `bookings`, and `members`; member exports are constrained to actor-related records.
- Evidence:
  - `repo/app/services/export_service.py:65`
  - `repo/app/services/export_service.py:78`
  - `repo/app/services/export_service.py:90`
  - `repo/app/services/export_service.py:108`
  - `repo/tests/test_exports/test_export_scope.py:58`
  - `repo/tests/test_exports/test_export_scope.py:84`
  - `repo/tests/test_exports/test_export_scope.py:142`
  - `repo/tests/test_exports/test_export_scope.py:169`

### 2. "Recent/trending shown locally on device" was server-side user/global logs, not device-local context
- Status: `Fixed`
- Rationale: Device-local flow is now statically complete across client header injection, API/view header pass-through, service/model device scoping, and dedicated device-scoped tests.
- Evidence:
  - `repo/templates/base.html:23`
  - `repo/templates/base.html:31`
  - `repo/app/models/search.py:13`
  - `repo/app/api/search.py:25`
  - `repo/app/api/search.py:51`
  - `repo/app/api/search.py:62`
  - `repo/app/views/search.py:42`
  - `repo/app/views/search.py:79`
  - `repo/app/services/search_service.py:301`
  - `repo/app/services/search_service.py:312`
  - `repo/app/services/search_service.py:334`
  - `repo/tests/test_search/test_recent_trending.py:87`
  - `repo/tests/test_search/test_recent_trending.py:106`

### 3. Staff booking list was restricted to creator/assigned photographer, weakening front-counter shared visibility
- Status: `Fixed`
- Rationale: Booking listing now explicitly allows both `admin` and `staff` to see all bookings; restrictions apply only to non-admin/non-staff roles.
- Evidence:
  - `repo/app/services/booking_service.py:287`
  - `repo/app/services/booking_service.py:293`

### 4. Test coverage missed export data-scope enforcement regression paths
- Status: `Fixed`
- Rationale: Regression coverage now includes non-admin scope checks for `orders`, `bookings`, and `members`.
- Evidence:
  - `repo/tests/test_exports/test_export_scope.py:58`
  - `repo/tests/test_exports/test_export_scope.py:84`
  - `repo/tests/test_exports/test_export_scope.py:142`
  - `repo/tests/test_exports/test_export_scope.py:169`
  - `repo/tests/test_exports/test_exports.py:29`

### 5. Session cookie hardening was incomplete in config defaults
- Status: `Fixed`
- Rationale: Secure defaults are present in base config, with explicit secure-cookie relaxation only in test config.
- Evidence:
  - `repo/config.py:30`
  - `repo/config.py:31`
  - `repo/config.py:32`
  - `repo/config.py:75`

### 6. Repository contains generated/runtime artifacts (`test_exports`, `__pycache__`)
- Status: `Fixed`
- Rationale: Previously cited artifact paths are absent in current snapshot, and ignore rules remain in place to prevent reintroduction.
- Evidence:
  - `repo/.gitignore:1`
  - `repo/.gitignore:13`
  - `repo/test_exports` (missing in snapshot)
  - `repo/__pycache__/config.cpython-313.pyc` (missing in snapshot)
  - `repo/app/__pycache__/__init__.cpython-313.pyc` (missing in snapshot)
  - `repo/tests/__pycache__/conftest.cpython-313-pytest-8.3.3.pyc` (missing in snapshot)

## Final Assessment

All six previously tracked issues are now fixed based on static repository evidence.

Static boundary still applies:

- This recheck did not execute the project or tests.
- Runtime behavior remains manual verification scope in general.
