const TG = 'https://api.telegram.org/bot';

async function tg(env, method, body = {}) {
  const r = await fetch(`${TG}${env.BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!r.ok) throw new Error(`Telegram ${method} failed: ${r.status}`);
  return r.json();
}

function mainMenu(role = 'viewer') {
  const rows = [
    [{ text: '📅 Ближайшие события', callback_data: 'events:list' }],
    [{ text: '🔔 Мои уведомления', callback_data: 'settings:notifications' }]
  ];
  if (['editor','admin','owner'].includes(role)) {
    rows.unshift([{ text: '➕ Создать публикацию', callback_data: 'broadcast:new' }]);
    rows.push([{ text: '📄 Мои публикации', callback_data: 'broadcast:mine' }]);
  }
  if (['admin','owner'].includes(role)) {
    rows.push([{ text: '✅ На согласовании', callback_data: 'review:list' }]);
    rows.push([{ text: '📣 Чаты и каналы', callback_data: 'targets:list' }]);
    rows.push([{ text: '📊 Аналитика', callback_data: 'analytics:main' }]);
  }
  return { inline_keyboard: rows };
}

async function ensureUser(env, u) {
  await env.DB.prepare(`INSERT INTO users (telegram_id, username, first_name, last_name)
    VALUES (?1, ?2, ?3, ?4)
    ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, last_name=excluded.last_name, updated_at=CURRENT_TIMESTAMP`)
    .bind(u.id, u.username || null, u.first_name || null, u.last_name || null).run();
  return env.DB.prepare('SELECT * FROM users WHERE telegram_id=?1').bind(u.id).first();
}

async function handlePrivateMessage(env, m) {
  const user = await ensureUser(env, m.from);
  if (m.text === '/start') {
    return tg(env, 'sendMessage', {
      chat_id: m.chat.id,
      text: 'Информационный бот Комиссии по взаимодействию с молодёжью. Здесь собраны мероприятия, возможности, регистрации и уведомления.',
      reply_markup: mainMenu(user.role)
    });
  }
  return tg(env, 'sendMessage', {
    chat_id: m.chat.id,
    text: 'Используйте меню ниже.',
    reply_markup: mainMenu(user.role)
  });
}

async function upsertTarget(env, chat, fromId = null) {
  const type = chat.type;
  if (!['group','supergroup','channel'].includes(type)) return;
  await env.DB.prepare(`INSERT INTO chats (chat_id, title, username, chat_type, added_by)
    VALUES (?1, ?2, ?3, ?4, ?5)
    ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, username=excluded.username, chat_type=excluded.chat_type, updated_at=CURRENT_TIMESTAMP`)
    .bind(chat.id, chat.title || String(chat.id), chat.username || null, type, fromId).run();
}

async function handleMyChatMember(env, update) {
  const chat = update.chat;
  const status = update.new_chat_member?.status;
  if (!['group','supergroup','channel'].includes(chat.type)) return;
  if (['administrator','member'].includes(status)) {
    await upsertTarget(env, chat, update.from?.id || null);
  } else if (['left','kicked'].includes(status)) {
    await env.DB.prepare("UPDATE chats SET status='disabled', bot_can_post=0, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?1")
      .bind(chat.id).run();
  }
}

async function handleCallback(env, q) {
  const user = await ensureUser(env, q.from);
  await tg(env, 'answerCallbackQuery', { callback_query_id: q.id });
  const chatId = q.message?.chat?.id;
  if (!chatId) return;

  if (q.data === 'broadcast:new') {
    if (!['editor','admin','owner'].includes(user.role)) return;
    await env.DB.prepare(`INSERT INTO user_states (telegram_id, state, payload_json)
      VALUES (?1, 'broadcast:title', '{}')
      ON CONFLICT(telegram_id) DO UPDATE SET state='broadcast:title', payload_json='{}', updated_at=CURRENT_TIMESTAMP`)
      .bind(user.telegram_id).run();
    return tg(env, 'sendMessage', { chat_id: chatId, text: 'Шаг 1/8. Отправьте название публикации.' });
  }

  if (q.data === 'analytics:main') {
    if (!['admin','owner'].includes(user.role)) return;
    const chats = await env.DB.prepare("SELECT COUNT(*) c FROM chats WHERE status='approved'").first();
    const pending = await env.DB.prepare("SELECT COUNT(*) c FROM broadcasts WHERE status='pending'").first();
    const published = await env.DB.prepare("SELECT COUNT(*) c FROM broadcasts WHERE status='published'").first();
    return tg(env, 'sendMessage', {
      chat_id: chatId,
      text: `📊 Аналитика\n\nПодключено чатов и каналов: ${chats?.c || 0}\nНа согласовании: ${pending?.c || 0}\nОпубликовано: ${published?.c || 0}`
    });
  }
}

async function processUpdate(env, update) {
  if (update.my_chat_member) return handleMyChatMember(env, update.my_chat_member);
  if (update.callback_query) return handleCallback(env, update.callback_query);
  if (update.message && update.message.chat.type === 'private') return handlePrivateMessage(env, update.message);
  if (update.message && ['group','supergroup'].includes(update.message.chat.type)) return upsertTarget(env, update.message.chat, update.message.from?.id || null);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/health') return new Response('ok');
    if (request.method !== 'POST') return new Response('Commission Youth Information Bot');
    const update = await request.json();
    await processUpdate(env, update);
    return new Response('ok');
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const due = await env.DB.prepare("SELECT id, broadcast_id FROM reminders WHERE status='scheduled' AND remind_at <= CURRENT_TIMESTAMP ORDER BY remind_at LIMIT 25").all();
      for (const reminder of due.results || []) {
        await env.DB.prepare("UPDATE reminders SET status='sending' WHERE id=?1").bind(reminder.id).run();
        // Delivery fan-out is implemented in the next milestone.
      }
    })());
  }
};
