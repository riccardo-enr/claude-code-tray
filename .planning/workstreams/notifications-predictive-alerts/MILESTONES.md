# Milestones

## v1.4 Session Dashboard (Shipped: 2026-07-20)

**Phases completed:** 3 phases, 8 plans, 8 tasks

**Key accomplishments:**

- Task 1 (`badde8a`)
- Task 1 (`ecc3e9a`)
- Task 1 (`cfc6a45`)
- Task 1 -- Tolerant config load + atomic config save.
- core.sess_notify_baseline seeds handle's notification baseline from a short-lived Monitor._reaped_status memory, so a genuinely-alive session reaped after 1h idle and resuming its same-status hook event reads as "no transition" instead of re-firing a "Waiting for input" popup -- restoring the NOTIF-02 de-dupe guarantee without touching session_stale.

---
