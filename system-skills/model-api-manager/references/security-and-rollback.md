# Security And Rollback

## Secrets

- Read keys from an environment variable or secure stdin only.
- Store Hermes keys in its `.env` with mode `0600` and reference them by name.
- Tavern stores its own server-side credential record and never exposes a full
  key through read endpoints.
- Logs and reports may contain only whether a key is set and a masked suffix.

## Atomic Changes

Before applying, snapshot the exact files affected in memory. Write Hermes
configuration through an atomic replacement. Let Tavern's registry own its own
atomic state update.

For target `both`, treat the operation as one transaction. If either validation
or write fails, restore Hermes config and Tavern model state to their original
bytes. Report the failure and the successful rollback; do not silently leave a
half-configured system.

## Recovery

If rollback itself fails, stop. Report the affected paths without printing their
contents or secrets. Do not continue with restarts, retries, fallback-provider
changes, or unrelated repairs.

Authentication failures require corrected credentials. Protocol failures require
the correct provider route or adapter. Timeouts may be retried once only when the
upstream failure is transient; configuration errors must not be retried blindly.

