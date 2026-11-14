# ERA bot and Mini App handoff

- 14 November: existing 12 December anniversary (screenshot title «12 декабря для ЭРА — особенная дата.») is featured above the Mini App home feed and first in the native bot reply menu. Mini App also registers from the participation card. Complete profile uses one tap, missing fields are collected in context.
- New anniversary entries from either surface use the existing guest RSVP store. Previous event registrations keep their status and appear in the deduplicated `/anniversary_guests` export. This change uses the existing event and does not activate the #670 publication/reminder campaign.
- Verify the exact PR head, main CI and automatic Render LIVE. Confirm the live event matches by date, start time and title or existing campaign marker. Keep production writes limited to genuine user actions.

- Owner priority (13 November): anniversary RSVP, 12 December 2026 at 17:30 Asia/Yerevan, cinema hall of Moscow House in Yerevan.
- #667 guest RSVP deep link `/start anniversary2026` and #668 event photo/direct links are already in main. Last verified Render LIVE before this change: `75f52fd952cc51ecf81ef64753511b58b6dcbfff`, deploy `dep-dbrnldff3r2c7391pe20`.
- AppSetting guest key is unique by Telegram sender; database upsert does not overwrite or duplicate existing registrations and commits before confirmation. Admin-only `/anniversary_guests` CSV export protects spreadsheet formulas.
- Existing B05 waitlist scoring #513 and E11 poster access #484/#486 remain; real multi-role/device acceptance is still unconfirmed. No changes to those policies in this RSVP task.
