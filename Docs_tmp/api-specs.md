# API Specifications — WildLifeLens Operations Suite

All JSON API routes are prefixed with `/api`. Every mutating request (`POST`, `PUT`, `DELETE`) must include `Content-Type: application/json`; requests without this header receive `415 Unsupported Media Type`. Authentication is session-based; unauthenticated requests to protected routes return `401`. Insufficient permissions return `403`.

---

## Authentication

### POST `/api/auth/register`
Register a new user. Assigns `member` role by default.

**Request**
```json
{ "username": "string", "password": "string" }
```
**Response `200`**
```json
{ "id": 1, "username": "alice", "roles": ["member"], "created_at": "2026-04-17T10:00:00" }
```
**Errors:** `400` username taken · `400` missing fields

---

### POST `/api/auth/login`
**Request**
```json
{ "username": "string", "password": "string" }
```
**Response `200`**
```json
{ "id": 1, "username": "alice", "roles": ["staff"] }
```
**Errors:** `401` invalid credentials

---

### POST `/api/auth/logout`
No body required. Session is invalidated.  
**Response `200`** `{ "message": "logged out" }`

---

### GET `/api/auth/me`
Returns the currently authenticated user.  
**Response `200`**
```json
{ "id": 1, "username": "alice", "roles": ["staff"], "created_at": "2026-04-17T10:00:00" }
```
**Errors:** `401` not logged in

---

## Users (admin only)

### GET `/api/users`
List all users.  
**Response `200`** `{ "results": [ <User>, … ] }`

### PUT `/api/users/{id}/roles`
Replace all roles for a user.  
**Request** `{ "roles": ["staff", "photographer"] }`  
**Response `200`** `<User>`  
**Errors:** `400` unknown role · `403` non-admin · `404` user not found

### POST `/api/users/{id}/roles`
Add a single role.  
**Request** `{ "role": "kitchen" }`  
**Response `200`** `<User>`

### DELETE `/api/users/{id}/roles/{role}`
Remove a single role.  
**Response `200`** `<User>`  
**Errors:** `404` role not assigned

---

## Members

### POST `/api/members`
Requires `member:create`.  
**Request**
```json
{
  "name": "Jane Doe",
  "phone_number": "5551234567",
  "member_id": "M-000001",
  "tier": "silver"        // optional; default "standard"
}
```
**Response `201`**
```json
{
  "id": 1,
  "name": "Jane Doe",
  "member_id": "M-000001",
  "phone_number": "***4567",   // masked for non-admin
  "tier": "silver",
  "points_balance": 0,
  "stored_value_balance": "***",
  "created_at": "2026-04-17T10:00:00"
}
```
**Errors:** `400` duplicate member_id or phone · `400` missing required fields

---

### GET `/api/members/search?q={query}`
Requires `member:view`. Fuzzy name/phone/member_id lookup. Phone results require decryption scan.  
**Response `200`**
```json
{ "results": [ <Member>, … ] }
```

---

### GET `/api/members/{id}`
Requires `member:view` + record-scope check.  
**Response `200`** `<Member>`  
**Errors:** `403` out-of-scope · `404` not found

---

## Orders

### POST `/api/orders`
Requires `order:create`.  
**Request**
```json
{
  "member_id": 1,
  "subtotal": 25.00,
  "discount": 0.0,           // optional
  "items": [                  // optional; used for KDS routing
    { "name": "Latte", "category": "drink", "price": 5.0, "quantity": 2 },
    { "name": "Burger", "category": "grill", "price": 15.0, "quantity": 1 }
  ]
}
```
**Response `201`**
```json
{
  "id": 1,
  "member_id": 1,
  "status": "created",
  "subtotal": 25.00,
  "discount": 0.0,
  "total": 25.00,
  "created_at": "2026-04-17T10:00:00",
  "deadline_at": "2026-04-17T10:30:00"
}
```
**Errors:** `400` member not found · `400` discount > subtotal · `400` tier cap exceeded

---

### GET `/api/orders/{id}`
Requires `order:view` + record-scope check.  
**Response `200`** `<Order>`  
**Errors:** `403` · `404`

---

### POST `/api/orders/{id}/pay`
Requires `order:pay`. Order must be in `created` status.  
**Request**
```json
{ "redeem_points": 5 }    // optional; integer points to apply (1 pt = $1, ≤20% cap)
```
**Response `200`** `<Order>` with `status: "paid"`  
**Errors:** `400` invalid transition · `400` insufficient points · `400` redemption cap exceeded · `403` scope · `404`

---

### POST `/api/orders/{id}/advance`
Requires `order:advance`. Advances through the state machine.  
**State machine:** `created → paid → in_prep → ready → delivered → reviewed`  
Also supports: `ready → ready_for_pickup → delivered`  
**Request** `{}`  
**Response `200`** `<Order>` with updated status  
**Errors:** `400` invalid/duplicate/final-state transition · `403` · `404`

---

### GET `/api/orders/{id}/receipt`
Requires `order:view` + record-scope.  
**Response `200`**
```json
{
  "order_id": 1,
  "member": { "name": "Jane Doe", "member_id": "M-000001" },
  "subtotal": 25.00,
  "discount": 0.0,
  "points_redeemed": 5,
  "total": 20.00,
  "status": "paid",
  "issued_at": "2026-04-17T10:05:00"
}
```

---

### GET `/api/orders/{id}/receipt/print`
Requires `order:view` + record-scope. Returns plain-text receipt suitable for thermal printing.  
**Response `200`** `text/plain`

---

## Schedules

### POST `/api/schedules`
Requires `schedule:create`.  
**Request**
```json
{
  "photographer_id": 3,
  "date": "2026-04-18",
  "start_time": "09:00",
  "end_time": "17:00",
  "type": "working"          // "working" | "break" | "off"
}
```
**Response `201`** `<Schedule>`  
**Errors:** `400` overlap · `400` invalid type · `404` photographer not found

---

### GET `/api/schedules`
Requires `schedule:view`. Optional query params: `photographer_id`, `date`.  
**Response `200`** `{ "results": [ <Schedule>, … ] }`

---

## Bookings

### POST `/api/bookings`
Requires `booking:create`. Validates against photographer schedule; rejects break/off overlaps.  
**Request**
```json
{
  "member_id": 1,
  "photographer_id": 3,
  "start_time": "2026-04-18T10:00:00",
  "end_time": "2026-04-18T11:00:00"
}
```
**Response `201`**
```json
{
  "id": 1,
  "member_id": 1,
  "photographer_id": 3,
  "start_time": "2026-04-18T10:00:00",
  "end_time": "2026-04-18T11:00:00",
  "status": "locked",
  "lock_expires_at": "2026-04-18T10:05:00",
  "created_at": "2026-04-17T10:00:00"
}
```
**Errors:** `400` schedule conflict · `400` photographer off/on-break · `400` time overlap with existing booking · `404` member/photographer not found

---

### GET `/api/bookings`
Requires `booking:view`. Admin and staff see all; photographers see their own.  
**Response `200`** `{ "results": [ <Booking>, … ] }`

---

### POST `/api/bookings/{id}/confirm`
Requires `booking:confirm` + record-scope. Booking must be `locked` and lock must not be expired.  
**Response `200`** `<Booking>` with `status: "confirmed"`  
**Errors:** `400` lock expired · `403` · `404`

---

### POST `/api/bookings/{id}/cancel`
Requires `booking:cancel` + record-scope.  
**Response `200`** `<Booking>` with `status: "cancelled"`  
**Errors:** `403` · `404`

---

## KDS (Kitchen Display System)

### GET `/api/kds`
Requires `kds:view`. Returns open tickets routed to stations.  
**Response `200`**
```json
{
  "results": [
    {
      "id": 1,
      "order_id": 1,
      "station": "bar",
      "items": [ { "name": "Latte", "category": "drink", "quantity": 2 } ],
      "status": "pending",
      "minutes_late": 0,
      "allergy_flags": [],
      "created_at": "2026-04-17T10:00:00"
    }
  ]
}
```

---

### POST `/api/kds/{id}/start`
Requires `kds:update`. Marks ticket as `in_progress`.  
**Request** `{}`  
**Response `200`** `<KDSTicket>`

---

### POST `/api/kds/{id}/complete`
Requires `kds:update`. Marks ticket `done`; writes back to order events; auto-advances order to `ready` when all tickets complete.  
**Request** `{}`  
**Response `200`** `<KDSTicket>`

---

## Search

### GET `/api/search?q={query}`
Requires `search:perform`. Supports keyword + synonym + pinyin fuzzy matching.  
Optional params: `category`, `taxonomy`, `region`, `habitat`, `size_range`, `protection_level`  
Device-scoped history recorded when `X-Device-ID` header is provided.  
**Response `200`**
```json
{
  "members": [ <Member>, … ],
  "orders": [ <Order>, … ],
  "catalog_items": [ <CatalogItem>, … ],
  "query_expanded": ["tiger", "laohu"]
}
```
Order results are gated by `order:view`; members are field-masked per actor scope.

---

### GET `/api/search/recent`
Requires `search:perform`. Returns recent searches for the current session.  
Send `X-Device-ID` header to scope results to a specific terminal.  
Optional: `?limit=10`  
**Response `200`**
```json
{ "results": [ { "id": 1, "query": "eagle", "user_id": 2, "device_id": "kiosk-1", "created_at": "…" } ] }
```

---

### GET `/api/search/trending`
Requires `search:trending`. Returns most-searched terms.  
Send `X-Device-ID` to get device-local trending instead of global.  
Optional: `?limit=10`  
**Response `200`**
```json
{ "results": [ { "query": "eagle", "count": 47 }, … ] }
```

---

## Clock-In / Clock-Out

### POST `/api/clock-in`
**Request**
```json
{
  "user_id": 2,
  "device_id": "kiosk-01",
  "face_image_hash": "sha256hex…",   // required in strict mode (default ON)
  "brightness": 0.75                 // capture brightness (0.0–1.0)
}
```
**Response `200`**
```json
{
  "status": "ok",
  "punch_id": 5,
  "signature": "hmac-sha256-hex…",
  "punched_at": "2026-04-17T09:00:00"
}
```
**Errors:** `400` brightness below threshold · `400` face match failed · `400` replay detected · `429` rate limit (3 per 5 min) · `403` device not enrolled

---

### POST `/api/clock-out`
Same request/response shape as `/api/clock-in`. Records a clock-out punch.

---

## Punch Corrections

### POST `/api/corrections`
Requires `correction:submit`.  
**Request**
```json
{
  "punch_id": 5,
  "requested_time": "2026-04-17T08:55:00",
  "reason": "kiosk was offline at actual punch time"
}
```
**Response `201`** `<Correction>` with `status: "pending"`

---

### GET `/api/corrections`
Requires `correction:view`. Admin sees all; others see own.  
**Response `200`** `{ "results": [ <Correction>, … ] }`

---

### POST `/api/corrections/{id}/approve`
Admin only. Creates a signed `TimePunch` using the full tamper-evident scheme.  
**Request** `{}`  
**Response `200`** `<Correction>` with `status: "approved"`

---

### POST `/api/corrections/{id}/reject`
Admin only.  
**Request** `{ "reason": "string" }` (optional)  
**Response `200`** `<Correction>` with `status: "rejected"`

---

## Enrollments (admin only)

### GET `/api/enrollments`
List all enrollments.  
**Response `200`** `{ "results": [ <Enrollment>, … ] }`

### GET `/api/enrollments/{user_id}`
Get the active enrollment for a user.  
**Response `200`** `<Enrollment>`  
**Errors:** `404`

### POST `/api/enrollments/{user_id}`
Create or replace enrollment. Deactivates any prior active enrollment.  
**Request**
```json
{
  "reference_hash": "sha256hex…",
  "device_id": "kiosk-01"
}
```
**Response `201`** `<Enrollment>`

### DELETE `/api/enrollments/{user_id}`
Deactivate (soft-delete) active enrollment.  
**Response `200`** `{ "message": "deactivated" }`

---

## Risk Flags

### GET `/api/risk`
Requires `risk:view`.  
**Response `200`** `{ "results": [ <RiskFlag>, … ] }`

### POST `/api/risk/{user_id}/clear`
Admin only. Clears all active risk flags for a user.  
**Response `200`** `{ "cleared": 2 }`

### POST `/api/risk/member/{member_id}/clear`
Admin only. Clears all active risk flags for a member.  
**Response `200`** `{ "cleared": 1 }`

---

## Exports

### POST `/api/exports`
Requires `export:create`. Generates a scoped CSV file. Non-admin exports are filtered to actor-linked records.  
**Request**
```json
{ "type": "orders" }    // "orders" | "members" | "bookings"
```
**Response `201`**
```json
{
  "id": 1,
  "user_id": 2,
  "type": "orders",
  "file_path": "exports/orders_20260417_100000.csv",
  "created_at": "2026-04-17T10:00:00"
}
```
**Errors:** `400` invalid type

---

### GET `/api/exports`
Requires `export:view`. Non-admin sees only own export jobs.  
**Response `200`** `{ "results": [ <ExportJob>, … ] }`

---

## Points

### POST `/api/points/redeem`
Requires `points:redeem` + record-scope on both member and order.  
**Request**
```json
{ "member_id": 1, "order_id": 1, "points": 5 }
```
**Response `200`**
```json
{ "points_redeemed": 5, "new_balance": 95, "discount_applied": 5.00 }
```
**Errors:** `400` insufficient points · `400` redemption cap exceeded (20% of order total) · `403` risk-flagged · `404`

---

### GET `/api/points/balance/{member_id}`
Requires `points:view`.  
**Response `200`** `{ "member_id": 1, "balance": 100 }`

---

### GET `/api/points/history/{member_id}`
Requires `points:view`.  
**Response `200`** `{ "results": [ { "id": 1, "delta": 10, "reason": "order_paid", "created_at": "…" }, … ] }`

---

## Stored Value

### POST `/api/stored-value/credit`
Requires `stored_value:credit` + record-scope.  
**Request**
```json
{ "member_id": 1, "amount": 50.00, "note": "initial load" }
```
**Response `200`** `{ "new_balance": 50.00 }`  
**Errors:** `400` invalid amount · `403` risk-flagged · `404`

---

### POST `/api/stored-value/debit`
Requires `stored_value:debit` + record-scope + risk-flag check.  
**Request**
```json
{ "member_id": 1, "amount": 10.00 }
```
**Response `200`** `{ "new_balance": 40.00 }`  
**Errors:** `400` insufficient balance · `403` risk-flagged · `404`

---

### GET `/api/stored-value/balance/{member_id}`
Requires `stored_value:view`. Balance is masked (`***`) for non-admin.  
**Response `200`** `{ "member_id": 1, "balance": "40.00" }`

---

### GET `/api/stored-value/history/{member_id}`
Requires `stored_value:view`.  
**Response `200`**
```json
{
  "results": [
    { "id": 1, "delta": -10.00, "balance_after": 40.00, "note": "", "created_at": "…" }
  ]
}
```

---

## Scope Permissions (admin only)

### GET `/api/permissions`
**Response `200`** `{ "results": [ <ScopePermission>, … ] }`

### POST `/api/permissions`
Grant a scope permission to a role.  
**Request**
```json
{
  "role": "staff",
  "resource": "member",
  "action": "view",
  "scope_type": "field",       // "location"|"station"|"employee"|"field"|"record"|"menu"|"api"
  "scope_value": "phone_number"
}
```
**Response `201`** `<ScopePermission>`

### DELETE `/api/permissions/{id}`
Revoke a scope permission.  
**Response `200`** `{ "message": "revoked" }`

---

## Tiers

### GET `/api/tiers`
Public (no auth). Returns all tier rules with benefit lists and discount caps.  
**Response `200`**
```json
{
  "results": [
    {
      "name": "silver",
      "description": "Silver membership",
      "benefits": ["5% discount", "early access"],
      "max_discount_pct": 5.0
    }
  ]
}
```

### GET `/api/tiers/{name}`
**Response `200`** `<Tier>`  
**Errors:** `404`

---

## Versioning (admin only)

### POST `/api/versions/{type}/{id}/snapshot`
Create a point-in-time snapshot. `type` is `member` or `order`.  
**Request** `{}`  
**Response `201`** `<Snapshot>`

### POST `/api/versions/{type}/{id}/rollback`
Restore entity to a prior snapshot.  
**Request** `{ "snapshot_id": 3 }`  
**Response `200`** `<Snapshot>`  
**Errors:** `400` snapshot not found or wrong entity · `404`

### GET `/api/versions?entity_type={type}&entity_id={id}`
List snapshots for an entity.  
**Response `200`** `{ "results": [ <Snapshot>, … ] }`

---

## Common Response Types

**`<User>`**
```json
{ "id": 1, "username": "alice", "roles": ["staff"], "created_at": "ISO8601" }
```

**`<Member>`**
```json
{
  "id": 1, "name": "Jane Doe", "member_id": "M-000001",
  "phone_number": "***4567", "tier": "silver",
  "points_balance": 100, "stored_value_balance": "***",
  "created_at": "ISO8601"
}
```

**`<Order>`**
```json
{
  "id": 1, "member_id": 1, "status": "paid",
  "subtotal": 25.00, "discount": 0.0, "total": 25.00,
  "created_at": "ISO8601", "deadline_at": "ISO8601 | null"
}
```

**`<Booking>`**
```json
{
  "id": 1, "member_id": 1, "photographer_id": 3,
  "start_time": "ISO8601", "end_time": "ISO8601",
  "status": "locked", "lock_expires_at": "ISO8601",
  "created_at": "ISO8601"
}
```

**`<Correction>`**
```json
{
  "id": 1, "punch_id": 5, "requested_time": "ISO8601",
  "reason": "string", "status": "pending|approved|rejected",
  "created_at": "ISO8601"
}
```

**`<Enrollment>`**
```json
{
  "id": 1, "user_id": 2, "device_id": "kiosk-01",
  "active": true, "created_at": "ISO8601"
}
```

**`<ExportJob>`**
```json
{
  "id": 1, "user_id": 2, "type": "orders",
  "file_path": "exports/orders_20260417_100000.csv",
  "created_at": "ISO8601"
}
```

**`<ScopePermission>`**
```json
{
  "id": 1, "role": "staff", "resource": "member",
  "action": "view", "scope_type": "field", "scope_value": "phone_number"
}
```

**`<Snapshot>`**
```json
{
  "id": 1, "entity_type": "member", "entity_id": 1,
  "data": { … }, "created_at": "ISO8601"
}
```

**`<KDSTicket>`**
```json
{
  "id": 1, "order_id": 1, "station": "bar",
  "items": [ { "name": "Latte", "category": "drink", "quantity": 2 } ],
  "status": "pending|in_progress|done",
  "minutes_late": 3, "allergy_flags": ["nut"],
  "created_at": "ISO8601"
}
```

**`<RiskFlag>`**
```json
{
  "id": 1, "user_id": 2, "member_id": null,
  "reason": "excessive_redemptions", "cleared": false,
  "created_at": "ISO8601"
}
```
