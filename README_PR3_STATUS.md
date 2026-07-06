# PR3 checkpoint

## Done

- Added partner data models: Partner, PartnerInitiative, PartnerTask.
- Registered partner tables in SQLAlchemy metadata.
- Added Alembic migration for partner tables: `0003_add_partners.py`.
- Added participant partner directory and partner cards with source link.
- Added active partner initiatives and partner tasks in partner cards.
- Added admin partner management flow:
  - list partners;
  - add partner;
  - view partner;
  - edit source link;
  - enable/disable;
  - archive.
- Added admin entry point under growth menu.
- Added partners entry in rewards/opportunities menu.
- Fixed reward auction keyboard rows.
- Added member point transfer flow:
  - /give_points command;
  - button in points hub;
  - recipient by username or Telegram ID;
  - amount validation;
  - balance check;
  - no self-transfer;
  - confirmation step;
  - creates negative transaction for sender and positive transaction for recipient.
- Added tests for partner models, partner keyboards, menu callbacks, and transfer states.

## Still needed before production merge

- GitHub Actions must be green.
- PR3 should be rebased after PR2 is merged, because migration `0003_add_partners.py` depends on `0002_social_profiles` from PR2.
- Keep transfer confirmation mandatory.
- Later: decide whether point transfers need daily limits or moderation for large transfers.
- Later: add richer partner mailing/export flow in a separate PR.
