# ERA Platform — Incident Response Runbook

Written to close `docs/FINAL_PRODUCTION_ACCEPTANCE.md`'s High finding #2
("no incident-response documentation exists"). This is a **procedure
document**, not a technical fix — it can't make an incident less likely by
itself, but it means the first 30 minutes of a real one aren't spent
figuring out what to do while also under pressure.

**What this document cannot do**: assign real people to roles, create
MFA/recovery codes on accounts it has no access to, or make organizational
decisions. Every `[OWNER: ...]` placeholder below needs the platform
owner to fill in once, then this becomes a real, usable runbook rather
than a template. See `docs/PRODUCTION_SERVICES_AND_OWNERS.md` for the
companion "who owns what" document this one assumes exists and is kept
current.

## Before an incident: minimum standing readiness

- [ ] `docs/PRODUCTION_SERVICES_AND_OWNERS.md` is filled in and current.
- [ ] At least two people can access each of: Render dashboard, GitHub repo
      admin, BotFather (the Telegram account that created the bot), the
      production Postgres connection string. A single point of failure
      here turns every scenario below into "wait for one specific person
      to be reachable."
- [ ] MFA enabled on GitHub, Render, and the Telegram account tied to
      BotFather, wherever the platform supports it.
- [ ] `docs/BACKUP_AND_RECOVERY.md`'s automated backup is actually
      succeeding (`gh run list --workflow=database-backup.yml` shows
      recent green runs, not just that the workflow file exists).

## General incident procedure

1. **Assess** — is this actively causing harm (data exposure, financial
   loss, ongoing unauthorized access) or is it contained (a past event,
   already stopped)? This determines whether step 2 happens in minutes or
   can wait for a calmer, more careful response.
2. **Contain** — stop the bleeding first, understand root cause second.
   Concretely: revoke/rotate the specific credential, not "redeploy
   everything and hope."
3. **Communicate** — tell `[OWNER: who else needs to know, and how]`
   before starting a fix that might cause visible downtime, not after.
4. **Fix** — the specific scenario sections below.
5. **Verify** — `/health`, `/ready`, `/diag` all confirm the expected
   state; re-run the relevant slice of
   `docs/FINAL_PRODUCTION_ACCEPTANCE.md`'s checklist for what was touched.
6. **Record** — see "Post-incident review" at the end of this document.

## Scenario 1: Telegram Bot Token leaked

**Signs**: an unexpected bot behavior, unauthorized messages sent as the
bot, or the token was accidentally posted somewhere (chat, commit, log).

1. Open @BotFather → the bot → **Revoke current token** (`/token` →
   `/revoke`). This immediately invalidates the leaked token — anyone
   holding it loses access the moment this completes.
2. Copy the new token BotFather issues.
3. Update `BOT_TOKEN` in Render Dashboard → `era-telegram-bot` →
   Environment. Render restarts the service automatically on save.
4. Confirm recovery: `curl https://<host>/diag` shows the expected
   `bot_id`/`bot_username` again (the ID doesn't change on token
   rotation, only the secret does — a mismatched `bot_id` here would mean
   something else is wrong, not this).
5. If the leak happened via Git (token committed, even briefly): the
   token is already invalidated by step 1, so history-scrubbing is not
   urgent for security, but still do a `git log -p | grep <old-token
   fragment>` sweep and, if found, treat it as a §XIII secret-scanning
   gap to close (see `docs/FINAL_PRODUCTION_ACCEPTANCE.md`).

## Scenario 2: Admin account compromise

**Signs**: unexpected role changes, unexpected point awards, unexpected
approvals/rejections in `AuditLog`, or a report from the account holder.

1. In Telegram, from another admin account: `admin:permissions` for the
   compromised account → revoke every `PermissionGrant`. If the
   compromised account is a full `admin` (in `ADMIN_IDS` or `User.role`),
   this requires a *different* full admin to act — this is exactly why
   §"Before an incident" above requires more than one.
2. Change `User.role` for the compromised account away from `admin` (via
   the Mini App Admin Mode's People section, or directly via a trusted
   admin session — not via the compromised account itself).
3. Review `AuditLog` for every action taken by that account since the
   suspected compromise time — `action` values like `user.role_changed`,
   `points.added`, `user.approved`/`rejected` are the ones with the most
   potential impact. Reverse anything clearly unauthorized (e.g. a
   fraudulent point award — issue a compensating negative
   `PointTransaction` with a matching `idempotency_key`, don't edit
   history).
4. If the compromise came from a leaked Telegram session (not just a
   guessed/phished credential), advise the account holder to check
   Telegram's own **Settings → Devices** and terminate unrecognized
   sessions — this app has no control over Telegram-level session
   security.
5. Rotate `MINIAPP_AUTH_SECRET` if there's any reason to believe Mini App
   session tokens themselves (not just the Telegram account) were
   exposed — this invalidates every active Mini App session platform-wide
   (documented trade-off, see `docs/PRODUCTION_READINESS_AUDIT.md`
   finding #12).

## Scenario 3: Production database leak/compromise

**Signs**: unexplained data changes, a report of user data appearing
somewhere it shouldn't, unauthorized connections in Render Postgres logs.

1. **Contain immediately**: Render Dashboard → `era-postgres` → rotate the
   database password/connection credentials. Update `DATABASE_URL`
   wherever it's configured (Render's own `fromDatabase` binding updates
   the web service automatically; any other consumer — e.g. a manual
   backup script run locally — needs the new value by hand).
2. Confirm no other services/scripts are still using the old credential
   (check `docs/PRODUCTION_SERVICES_AND_OWNERS.md` for anything with DB
   access).
3. Assess scope: which tables, how far back, whether it includes
   `PersonalData`-category fields per `docs/DATA_INVENTORY.md` §1.
4. If personal data was exposed: this becomes a legal-notification
   question, not just a technical one — see
   `docs/DATA_INVENTORY.md`/`docs/PRIVACY_POLICY_DRAFT.md`'s own
   disclosure that this decision needs the platform owner and, per the
   final checklist's own rule, a lawyer where applicable jurisdiction
   requires it. Don't decide unilaterally whether affected users need to
   be told — that's `[OWNER ACTION REQUIRED]`, tracked here so it isn't
   silently skipped under pressure.
5. Restore from the last verified-good backup if data integrity (not just
   confidentiality) is in question — see
   `docs/BACKUP_AND_RECOVERY.md`'s "Восстановление"/"Откат" procedure.
6. Preserve evidence (a copy of the compromised state, Render access
   logs if available) before remediating, in case root-cause analysis or
   a legal process needs it later.

## Scenario 4: Hosting provider (Render) unavailable

**Signs**: `/health` unreachable, Render status page shows an incident,
deploys stuck.

1. Check [Render's own status page] before assuming it's this app's fault
   — `[OWNER: add the actual status-page URL here]`.
2. If it's a Render-wide outage: there is currently no secondary hosting
   target configured (`docs/DEPLOYMENT_RUNBOOK.md`'s topology is
   single-provider by design) — the honest answer is "wait for Render,"
   not "fail over," unless the owner decides a multi-provider setup is
   worth the added complexity for this platform's actual uptime needs.
3. If it's specific to this service (not Render-wide): check Render
   Dashboard → `era-telegram-bot` → Events/Logs for a crash loop,
   failed health check, or resource limit (the `free` plan in
   `render.yaml` has real memory/CPU ceilings).
4. Once service is restored: run the smoke test from
   `docs/DEPLOYMENT_RUNBOOK.md`'s "Smoke test после деплоя" section
   before considering the incident closed.

## Post-incident review

For any incident that reached "Contain" or further above, record — in a
new dated entry appended to this file's "Incident log" section below —
at minimum: what happened, when noticed vs. when it started (if
determinable), what was done, what the actual root cause was (not just
the trigger), and one concrete change (code, process, or monitoring) that
would have caught it sooner or prevented it. This is what closes
`docs/FINAL_PRODUCTION_ACCEPTANCE.md` item #285 in practice, not just in
principle — an unused template doesn't count.

## Incident log

*(No incidents recorded yet. This section exists so the first one has
somewhere to go without inventing the format under pressure.)*
