# Journal security setup and paid-beta launch checklist

## What this release changes immediately

- **Hide P&L** in the header hides only the headline Net P&L value. Other statistics, trade amounts, charts, goal progress, notes, and calendar colours remain visible. The device remembers the choice before data renders, including on reload. This is limited shoulder-surfing protection, not an account lock or encryption of page data.
- Browser-persisted IBKR reporting tokens are removed. Reconnect in Settings. Until the vault is activated, a token exists only in that tab's memory and is sent over HTTPS through the journal server to IBKR. Reloading or closing the tab clears it. No broker trading password is needed.
- Journal API requests verify identity, restrict browser origins, cap uploads at 2 MB and 20,000 fills, limit requests, reject XML entities, and return safe errors. Production pages fail closed if authentication configuration fails.
- The journal has a Content Security Policy, pinned external scripts with integrity checks, and escaping of imported strings. Local development authentication requires an explicit loopback-only switch. Deployment excludes private files and blocks private/source-file URLs.
- The code is ready for encrypted broker storage, database-backed preferences/stars, and distributed rate limits. Production configuration was activated on 17 September 2026 after the migration and live isolation tests passed. Other environments require the steps below. Before activation, preferences/stars retain the existing metadata storage and rate limits are per server process, not global.

## 1. Back up and apply the database migration

1. In Supabase, confirm you have a recent database backup and a documented way to restore it. A backup existing is not proof a restore works: restore a copy into a separate test project before the paid beta.
2. Open the SQL Editor for the correct Option Riders project.
3. Run `supabase/migrations/20260917_journal_security.sql` and then `supabase/migrations/20260917_journal_function_hardening.sql` from this repository. It creates the encrypted connection table, user-owned preferences and daily reviews, and the rate-limit function. It copies valid existing targets and stars without overwriting newer rows. It retains old metadata for rollback.
4. Check Supabase Security Advisor. Confirm row-level security is enabled for `journal_fills`, `journal_notes`, `journal_preferences`, `journal_discipline`, and `journal_connections`.
5. Do not grant `anon` or `authenticated` access to `journal_connections`. Only the backend service role can retrieve its ciphertext. Never expose the service-role key in the browser.

Keep the interval between migration and activation short: edits made to legacy metadata during the gap are not copied by rerunning an insert-only backfill. For a populated public beta, schedule a brief journal maintenance window or reconcile those edits before switching. Existing users should reload after activation; stale tabs may continue using the old metadata path until reloaded.

## 2. Configure Vercel secrets and activate

In the existing Vercel project's **Settings → Environment Variables**, select Production:

| Name | Value |
| --- | --- |
| `JOURNAL_VAULT_KEY` | A new random 32-byte key, base64 encoded. Generate locally with `openssl rand -base64 32`; paste directly into Vercel and keep a backup in your password manager. Never put it in Git, chat, or a public browser variable. |
| `JOURNAL_SECURITY_STORAGE` | `1`, only after the SQL migration succeeds. |
| `SUPABASE_SERVICE_ROLE_KEY` | Verify the existing private service-role key points to the same Supabase project. |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Verify the existing project values. The anon key is public by design; database policies provide protection. |
| `APP_URL` | `https://www.optionriders.com` (or the exact production origin you use). |

Redeploy the latest commit after saving these variables. Preview deployments should use a separate Supabase project and their own key. Do not share production broker credentials with preview environments.

In the journal, reload, open Settings, and reconnect IBKR. The status should say credentials are saved encrypted. Close and reopen the browser; syncing should still work without entering a token. The Settings form must never return the stored token. Test Disconnect and confirm subsequent sync requires reconnecting.

Do not replace the encryption key casually: existing ciphertext cannot be decrypted with a different key. For emergency rotation, revoke the affected IBKR reporting tokens, remove stored connections, rotate the server key, and ask users to reconnect. For planned rotation, use a reviewed decrypt/re-encrypt migration. Store the key separately from database backups.

## 3. Run the live isolation check

This is intentionally **not run automatically** against production. Prefer a test project first. The test creates two temporary users, inserts only their test data, checks both directions of cross-account access, and deletes those users and rows. It sends no welcome emails. Email/password authentication must be enabled for these synthetic test accounts.

From the repository, with the existing virtual environment and an environment file containing the correct Supabase URL, anon key, and service-role key:

```sh
.venv/bin/python tests/verify_journal_isolation.py --run-live --env-file .env
```

The test checks own access, anonymous reads, forged ownership, cross-account reads, updates and deletes, ownership changes, and blocked browser access to the encrypted token table. It never prints passwords or tokens. A failure blocks launch; check the named policy and rerun. If cleanup fails, it prints only temporary user IDs for manual removal.

Also check the journal in two separate browser profiles: log in as A and B, add different notes/targets/stars, and verify switching accounts, refreshing expired sessions, and opening day/week details never shows the previous user's data. Test expired and missing tokens against the APIs. Verify anonymous database RPCs cannot expose account data, including existing analytics functions and views. The automated test is necessary but not a complete penetration test.

## 4. Verify the release with a browser

- On desktop and mobile, hide P&L and reload. The headline Net P&L should remain hidden while every other statistic, trade amount, chart, goal, note, and calendar colour remains visible. Show P&L restores the headline value. The preference is device-wide.
- Test Google sign-in, note editing, chart rendering/fallback, FX conversion, target saves and daily stars. Inspect the console for Content Security Policy errors.
- Check oversized or malformed imports produce a friendly rejection without exposing internal errors.
- With distributed storage enabled, repeated sync attempts should be throttled. Protect anonymous traffic and expensive public market-data endpoints separately with Vercel firewall/rate-limit rules and spending alerts. App-level user quotas do not replace infrastructure-level abuse controls.

## 5. Required before a paid launch

These items remain operator/business work; this code release does not certify them complete:

- Require MFA on GitHub, Vercel, Supabase, Stripe and the administrative email account; remove unnecessary collaborators. Decide and implement customer MFA/recovery/session-revocation policy.
- Commission an independent security review covering tenant isolation, direct PostgREST access, existing RPCs/views, imports, script injection, session handling, billing and infrastructure. The author of these changes is not an independent reviewer.
- Configure monitoring for auth failures, errors, sync failures, rate limits and spending. Keep broker tokens, bearer tokens and trade-report bodies out of logs. Document who responds to an incident, how to revoke tokens, and how to notify affected users when required.
- Rehearse backup restoration; document recovery-time and data-loss targets.
- Implement and test account export/deletion, retention periods, privacy notice, subprocessors and applicable privacy obligations with appropriate advice. Deleting an account must also remove broker connections and app data, with a documented backup-retention policy.
- Decide the journal's product/price and paid-access policy. The existing dashboard subscription is **not a journal paywall**. Enforce paid entitlements on the server **and direct database access paths**; never in user-editable metadata. Preserve appropriate export/deletion access after cancellation. Test Stripe duplicate/out-of-order events, renewal failures, expiry and cancellation before charging users.
- Run a small beta only after the critical security checks pass; validate import accuracy and support load before a wider launch.

## Rollback

For a functional rollback, prefer rolling back application code while retaining the new tables and encrypted data. Setting `JOURNAL_SECURITY_STORAGE=0` returns to legacy metadata and tab-only broker tokens; new database-only target/star changes will not be visible in that mode, so export/reconcile them first. Never work around a storage outage by granting broad database access. With the flag enabled, distributed-rate-limit/storage failures intentionally fail closed.

## Validation record

Local automated checks cover encryption/tampering/wrong-user decryption, input boundaries, origin rejection, token-safe error responses, credential ownership, local/distributed quota behaviour, privacy persistence, browser-token cleanup, escaping and database-backed preferences. Live verification on 17 September 2026:

- Applied the additive migration to the verified production project; all seven public tables have row-level security enabled.
- Passed two-user own-access, cross-account read/update/delete, forged ownership, ownership-transfer, anonymous-read, and blocked direct-vault-read checks. Temporary users and their fixtures were removed.
- Passed an encrypted broker save/load/disconnect round trip against production storage using synthetic credentials, wrong-user decryption rejection, distributed sync throttling, and anonymous quota-RPC denial. The temporary account was removed. No broker request was sent.
- Inspected the existing statistics function: it uses caller privileges rather than security-definer privileges. No public views were present.
- Configured the encryption key as a production-only Vercel secret, plus the storage activation flag and production origin. A restricted local recovery copy of the key is kept outside the repository; transfer it to the owner's password manager. Never commit or display it.
- Resolved the security advisor warnings for mutable function search paths. The remaining quota-function warning is intentional: it uses the authenticated caller ID and exposes no journal records. Leaked-password protection is disabled and remains an operator action.
- Supabase reported no available backups and point-in-time recovery disabled. Backup setup and a restore rehearsal remain outstanding.
- Browser interaction testing, an actual user IBKR reconnect/sync, and an independent security review remain outstanding. This is not a paid-launch security certification.

References: [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security), [OWASP browser storage](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html), [Stripe webhook verification](https://docs.stripe.com/webhooks), [MDN CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP).
