# PostgreSQL external ingress — 21.10.2026

Target: existing `era-postgres` / `dpg-d91r19vavr4c73fs837g-a`, Frankfurt, David's workspace. Do not create, rename, replace or delete the database.

## Checked before change

- Live public allowlist is `0.0.0.0/0`; current application connections are private `10.x` clients.
- The existing bot service receives its database URL through `fromDatabase.connectionString` in the same region. Startup migrations and snapshot export run inside that service.
- GitHub migration CI uses its isolated PostgreSQL service. Backup downloads a transient production snapshot through the OIDC-protected HTTPS endpoint, not through public PostgreSQL.
- Backup run `39552815304` (21.10 06:00 UTC) successfully restored the current production snapshot into isolated PostgreSQL 18 before encryption and GitHub artifact upload.

## Desired change

Only add `databases[era-postgres].ipAllowList: []` to the existing Blueprint. Render's current Blueprint specification defines this as internal-only database access. Do not change the web service's public HTTP ingress, private database wiring, credentials, plan, schema or data.

## Acceptance after merge/sync

1. Verify the existing Blueprint sync actually applied to this database; a code merge alone is not evidence of a live ACL change.
2. Read the live database and confirm `ipAllowList=[]` and `status=available`.
3. Confirm `/health`, `/ready`, primary `@ERA_1bot` webhook and recent logs remain healthy. Commission is a separate poller, not the primary ERA identity.
4. Confirm the next OIDC backup snapshot and isolated restore succeed. Preserve the last verified artifact until then.

If Blueprint sync is not connected or fails, leave the item open and request an authorized Dashboard/admin action. Do not work around read-only SQL or claim the public network is already closed. For any confirmed external operational client, obtain its fixed CIDR and use a narrow documented rule instead of restoring world access.

References checked directly: https://render.com/docs/blueprint-spec.md (Postgres fields, inbound IP rules), https://render.com/docs/private-network.md.
