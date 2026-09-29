PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  telegram_id INTEGER PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  last_name TEXT,
  role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('viewer','editor','admin','owner')),
  country TEXT,
  phone TEXT,
  notifications_enabled INTEGER NOT NULL DEFAULT 1,
  whatsapp_opt_in INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_states (
  telegram_id INTEGER PRIMARY KEY,
  state TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chats (
  chat_id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  username TEXT,
  chat_type TEXT NOT NULL CHECK(chat_type IN ('group','supergroup','channel')),
  country TEXT,
  network TEXT NOT NULL DEFAULT 'commission' CHECK(network IN ('commission','mds')),
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','disabled','rejected')),
  bot_can_post INTEGER NOT NULL DEFAULT 1,
  added_by INTEGER,
  approved_by INTEGER,
  approved_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS broadcasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  photo_file_id TEXT,
  starts_at TEXT NOT NULL,
  registration_url TEXT,
  country_scope TEXT NOT NULL DEFAULT 'ALL',
  network_scope TEXT NOT NULL DEFAULT 'commission' CHECK(network_scope IN ('commission','mds','both')),
  personal_scope INTEGER NOT NULL DEFAULT 1,
  whatsapp_duplicate INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','pending','approved','publishing','published','rejected','cancelled')),
  created_by INTEGER NOT NULL,
  approved_by INTEGER,
  approved_at TEXT,
  published_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(telegram_id)
);

CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id INTEGER NOT NULL,
  remind_at TEXT NOT NULL,
  offset_minutes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled','sending','sent','failed','cancelled')),
  sent_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS registrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id INTEGER NOT NULL,
  telegram_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'registered',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(broadcast_id, telegram_id),
  FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE,
  FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  broadcast_id INTEGER NOT NULL,
  reminder_id INTEGER,
  platform TEXT NOT NULL CHECK(platform IN ('telegram','whatsapp')),
  destination_type TEXT NOT NULL CHECK(destination_type IN ('chat','user')),
  destination_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('sent','failed','skipped')),
  error_text TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_users_country ON users(country);
CREATE INDEX IF NOT EXISTS idx_chats_status_country ON chats(status, country);
CREATE INDEX IF NOT EXISTS idx_broadcasts_status ON broadcasts(status);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, remind_at);
CREATE INDEX IF NOT EXISTS idx_delivery_broadcast ON delivery_log(broadcast_id);
