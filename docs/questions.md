## Business Logic Questions Log (Simplified Format)

### 1. What does "fully offline" include?

* **Problem:** Offline could mean no internet only, or also no external APIs, cloud AI, or third-party services.
* **My Understanding:** The system must run entirely on a local machine or LAN without external dependencies.
* **Solution:** Use only local resources (Flask, SQLite, local file storage, local face matching), no external APIs.

---

### 2. How should face recognition be implemented locally?

* **Problem:** The prompt specifies face-match threshold (0.85) but not the algorithm/library.
* **My Understanding:** Must be lightweight and runnable offline.
* **Solution:** Use a local library (e.g., OpenCV + face embeddings) with stored reference images and cosine similarity.

---

### 3. How are device fingerprints generated?

* **Problem:** Device fingerprinting method is not defined.
* **My Understanding:** Must uniquely identify the kiosk/device without external services.
* **Solution:** Generate hash from machine-specific attributes (MAC, hostname, OS info) and store locally.

---

### 4. How are "trending searches" calculated offline?

* **Problem:** Trending usually requires global data, but system is offline.
* **My Understanding:** Must be based on local usage.
* **Solution:** Track recent searches in SQLite and compute frequency-based ranking.

---

### 5. What defines a "conflict" in photographer scheduling?

* **Problem:** Overlap rules and buffer times are not specified.
* **My Understanding:** Conflicts occur when time ranges overlap.
* **Solution:** Prevent overlapping bookings; optionally enforce configurable buffer time between sessions.

---

### 6. How should the 5-minute booking lock behave?

* **Problem:** Lock expiration and concurrency behavior unclear.
* **My Understanding:** Temporary reservation to prevent double booking.
* **Solution:** Store lock with timestamp; auto-expire after 5 minutes; enforce via DB constraint + validation.

---

### 7. How are order status transitions enforced?

* **Problem:** Allowed transitions are mentioned but not explicitly defined.
* **My Understanding:** Must follow a strict state machine.
* **Solution:** Define explicit transition map (e.g., created → paid → in-prep → ready → delivered → reviewed).

---

### 8. How should KDS routing by category work?

* **Problem:** Mapping between items and kitchen stations is not defined.
* **My Understanding:** Each item belongs to a category linked to a station.
* **Solution:** Maintain category → station mapping table and route tickets accordingly.

---

### 9. What qualifies as "high-risk behavior" blocking redemption?

* **Problem:** Rules are given but handling flow is unclear.
* **My Understanding:** System should block further redemption until admin action.
* **Solution:** Flag user in DB and enforce checks before redemption; require admin clearance.

---

### 10. How should encryption at rest be implemented?

* **Problem:** Encryption method and key management not specified.
* **My Understanding:** Must be local and secure.
* **Solution:** Use application-level encryption (e.g., AES) with a locally stored secret key (env/config).

---

### 11. How should audit logs be structured?

* **Problem:** Level of detail and immutability mechanism unclear.
* **My Understanding:** Must support traceability.
* **Solution:** Append-only audit table with actor, action, timestamp, and before/after snapshots.

---

### 12. How should clock-in failure feedback be determined?

* **Problem:** Multiple validation checks exist but pass/fail logic unclear.
* **My Understanding:** All checks must pass.
* **Solution:** Fail if any condition fails (face mismatch, brightness, multiple faces, rate limit).

---

### 13. How are points expiration handled?

* **Problem:** Whether expiration is batch or real-time is unclear.
* **My Understanding:** Must be accurate during transactions.
* **Solution:** Compute expiration dynamically during redemption and via scheduled cleanup.

---

### 14. How should unpaid order auto-cancel work?

* **Problem:** Background job mechanism not defined.
* **My Understanding:** Needs time-based automation.
* **Solution:** Use background scheduler to mark orders canceled after 30 minutes.

---

### 15. How should "smart filters" for search be implemented?

* **Problem:** Filtering logic and indexing strategy not specified.
* **My Understanding:** Must be fast and flexible.
* **Solution:** Use indexed fields + LIKE queries + optional FTS (SQLite full-text search).


### 16. What is the required depth of the UI implementation?

* **Problem:** The prompt mentions HTMX-based UI but does not define how complete or polished it should be.
* **My Understanding:** The UI should be functional but not production-polished.
* **Solution:** Implement minimal but complete workflows (member lookup, order creation, scheduling, clock-in) using simple Jinja templates and HTMX interactions.

---

### 17. Should the UI cover all domains or only key workflows?

* **Problem:** It is unclear whether every backend feature requires a UI.
* **My Understanding:** Only critical operational flows need UI coverage.
* **Solution:** Provide UI for core workflows: member lookup, order lifecycle, booking, KDS view, and clock-in. Admin/config flows can remain API-only.

---

### 18. How should HTMX interactions be structured?

* **Problem:** The prompt does not specify whether full-page reloads or partial updates are required.
* **My Understanding:** HTMX should be used for partial updates to simulate SPA-like responsiveness.
* **Solution:** Use HTMX attributes (hx-get, hx-post, hx-target) and return partial HTML fragments from Flask routes.

---

### 19. How should frontend testing be implemented?

* **Problem:** The company requires frontend tests, but no framework is specified.
* **My Understanding:** Testing must remain within Python ecosystem.
* **Solution:** Use Flask test client to validate rendered HTML responses and key UI flows, asserting presence of expected elements and dynamic updates.

---

### 20. What level of styling is required?

* **Problem:** No requirement for CSS/UI design is specified.
* **My Understanding:** Styling is not the focus of evaluation.
* **Solution:** Use minimal styling (basic CSS or none); prioritize functionality over design.

---

### 21. Should HTMX views and API endpoints be separated?

* **Problem:** It is unclear whether the same endpoints should serve both API and UI.
* **My Understanding:** Separation improves clarity and testing.
* **Solution:** Maintain separate routes for API (JSON) and HTMX views (HTML responses), sharing service logic underneath.

---

### 22. How should KDS UI behave in an offline environment?

* **Problem:** Real-time updates are mentioned but no mechanism is specified.
* **My Understanding:** Must work without WebSockets or external services.
* **Solution:** Use HTMX polling (hx-trigger="every Xs") to refresh KDS screen periodically.

---

### 23. How should countdown timers (order expiry, booking lock) be displayed?

* **Problem:** The prompt mentions countdown badges but not implementation details.
* **My Understanding:** Needs near real-time updates without external services.
* **Solution:** Compute remaining time server-side and update via HTMX polling or lightweight client-side JS timers.

---

### 24. Should search UI support real-time suggestions?

* **Problem:** The prompt mentions trending and recent searches but not interaction style.
* **My Understanding:** Must feel responsive but remain simple.
* **Solution:** Implement HTMX-based live search with debounced requests and local database queries.

---

### 25. What level of E2E testing is required?

* **Problem:** Company requires E2E tests but tooling is not specified.
* **My Understanding:** Must stay within Python environment.
* **Solution:** Simulate full workflows (login → create order → advance status) using Flask test client to emulate end-to-end behavior.
