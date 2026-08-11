# ERA Platform — Production Services & Owners

Closes `docs/FINAL_PRODUCTION_ACCEPTANCE.md` item #278 (and feeds items
#271–277). This is a structural template with every real service this
platform actually depends on — filling in the `[OWNER: ...]` /
`[ACCOUNT: ...]` placeholders is the one remaining step, and it's the
platform owner's, not a technical one: nothing in this codebase or this
session's tooling has visibility into who holds which account.

**Keep this current.** A services list that's six months stale during a
real incident is only slightly better than no list — update it whenever
an owner or account changes, not just once at launch.

| Service | What it's for | Owner | Account / access | MFA enabled | Recovery codes stored |
|---|---|---|---|---|---|
| **Render** (hosting: web service, Postgres, Redis) | Runs the entire application — see `render.yaml` | `[OWNER: name]` | `[ACCOUNT: email/org]` | `[OWNER: yes/no]` | `[OWNER: where, e.g. password manager name — not the codes themselves]` |
| **GitHub** (`davidbagh22/era-telegram-bot`) | Source of truth for all code; CI/CD triggers Render deploys on push to `main` | `[OWNER: name]` | `[ACCOUNT: username]` | `[OWNER: yes/no]` | `[OWNER: where]` |
| **BotFather / Telegram** (the account that created @ERA_1bot) | Controls the bot token, Mini App URL registration, bot profile settings — the one account this entire platform's identity depends on | `[OWNER: name]` | `[ACCOUNT: Telegram phone/username]` | `[OWNER: Telegram 2FA enabled? yes/no]` | `[OWNER: where]` |
| **Production Postgres** (`era-postgres` on Render) | All user/business data | `[OWNER: name — may be the same as Render owner]` | Connection string in Render's `DATABASE_URL` binding; direct external access needs a separately-issued connection string | N/A (DB credential, not an MFA-capable login) | `[OWNER: connection string stored where]` |
| **GitHub Actions secrets** (`BACKUP_DATABASE_URL` and any future ones) | Backup pipeline, CI | `[OWNER: name — needs GitHub repo admin]` | Settings → Secrets and variables → Actions | N/A (inherits GitHub account MFA) | — |
| **`ADMIN_IDS`** (Telegram ID(s) with full platform admin role) | `render.yaml`'s `ADMIN_IDS` env var — currently a single Telegram ID | `[OWNER: confirm who this ID belongs to]` | The Telegram account itself | Telegram's own 2FA | — |

## Single-point-of-failure check

As of this document's writing, `render.yaml`'s `ADMIN_IDS` contains
exactly **one** Telegram ID, and no second named owner appears anywhere
in the codebase for Render, GitHub, or BotFather. Per
`docs/FINAL_PRODUCTION_ACCEPTANCE.md` finding High #2, this is a real
risk for the platform's "must survive unattended" requirement — if that
one person is unreachable during an incident, `docs/INCIDENT_RESPONSE_RUNBOOK.md`'s
Scenario 2 (admin compromise) specifically cannot be executed, since it
requires a *second* admin account to act.

**Recommended minimum**: at least one second person with admin role in
the platform itself (`User.role = admin` or a full `PermissionGrant`
set), and at least one second person with Render/GitHub dashboard access.
This is an organizational decision for the owner, not something this
document can complete on its own.

## How this connects to other docs

- `docs/INCIDENT_RESPONSE_RUNBOOK.md` — the procedures that assume this
  list is accurate.
- `docs/DEPLOYMENT_RUNBOOK.md` — day-to-day operational reference for the
  same services.
- `docs/BACKUP_AND_RECOVERY.md` — depends on the GitHub Actions secret
  listed above actually being set (see
  `docs/FINAL_PRODUCTION_ACCEPTANCE.md`'s Critical finding).
