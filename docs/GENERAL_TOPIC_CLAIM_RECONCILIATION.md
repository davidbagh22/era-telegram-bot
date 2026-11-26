# General forum topic claim reconciliation — safety gate

**Scope:** `@ERA_1bot` only, `general_forum:<general_chat_id>:<key>` settings. Never apply this procedure to `@MVKSRS_bot` or the Commission database.

**Status:** operational design / approval checklist, **not an authorized production repair**. The proposed durable-claim code is in DRAFT PR #578 and is **not released**. Do not treat this document as permission to create/delete topics, edit Telegram roles, or modify production rows.

## Why a claim is ambiguous

A `{"state":"creating"}` row means the claim was durably committed before calling Telegram. It does **not** prove whether Telegram created the topic: the process can crash before the request, the response can be lost after remote creation, or the database acknowledgement can fail. Automatically clearing or retrying the claim can create duplicate public forum topics and misroute announcements. Fail closed until reconciled.

## Read-only evidence collection

1. Identify the exact deployment SHA, application version, target chat ID, topic key and setting key; confirm this is the ERA general chat, not the leaders/media forum and not Commission. Use the current checkpoint and Render/GitHub, not historical SHA.
2. Record the **redacted** state and timestamp of the AppSetting row with a read-only database session. A missing row is different from `creating`, malformed JSON, and a saved positive `thread_id`. Never paste Telegram tokens or participant data into tickets.
3. Ask an authorized human administrator to inspect the **actual target forum** in the Telegram client and record the visible topic name, message-thread ID (verified by an authorized bot/API method if necessary), and any duplicate candidates. A matching topic title alone is insufficient to identify a thread ID.
4. Correlate the request time with Telegram API logs and Render deploy/crash logs. An API timeout is **not** evidence that the topic was not created. If the remote outcome cannot be independently verified, leave the claim unchanged.
5. Preserve the evidence and the desired destination in a restricted change ticket; have a second authorized reviewer verify the chat ID, topic ID, and evidence.

## Authorized repair preconditions (not implemented)

- Explicit owner approval for a narrowly scoped production AppSetting change; a separate explicit approval for any Telegram topic or role mutation. The normal automation is **not authorized** to perform these actions.
- An independently verified existing Telegram thread ID in the correct chat. If no topic exists, the owner must separately approve a controlled new creation; never let a background retry infer that approval.
- Tested, current backup and documented rollback plan; check independent offsite restoration separately. No destructive SQL, mass sends, points changes, or changes to other AppSetting keys.
- A purpose-built repair operation must compare the exact old row value and chat/key, validate the positive integer thread ID, and perform an audited conditional update in one transaction. If the old row changed, abort. Verify the resulting route read-only before allowing normal sends.
- Reconciliation must never silently rewrite an existing valid route or treat a deleted/missing topic as safe to recreate. Do not repair by deleting the `creating` row.

## Acceptance required before merging PR #578

- Exact-head Bot checks 5/5 and Tests 1/1, including isolated PostgreSQL race proof and rollback/claim-failure tests.
- A documented and **implemented** authorized reconciliation mechanism with audit trail, scoped permission, compare-and-swap, and a safe dry-run; approval by the ERA owner.
- Real, explicitly authorized Telegram forum acceptance with at least two workers and a simulated lost response; verify no duplicate topic and no fallback to the main thread. Code mocks and logs alone are not real acceptance.
- Device/role checks for participants and administrators; no unauthorized send or topic mutation during routine CI.

**Current policy:** preserve ambiguous claims and escalate to an authorized administrator. This prevents automatic duplicates at the cost of temporarily unavailable topic routing. The trade-off is deliberate and remains a release blocker until reconciliation is operational.
