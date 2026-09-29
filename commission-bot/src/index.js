const TG = 'https://api.telegram.org/bot';
const GRAPH = 'https://graph.facebook.com';

async function tg(env, method, body = {}) {
  const r = await fetch(`${TG}${env.BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.ok === false) throw new Error(`Telegram ${method}: ${data.description || r.status}`);
  return data;
}

function esc(s = '') {
  return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
}

function isStaff(role) { return ['editor','admin','owner'].includes(role); }
function isAdmin(role) { return ['admin','owner'].includes(role); }

function mainMenu(role = 'viewer') {
  const rows = [
    [{ text: '📅 Ближайшие события', callback_data: 'events:list' }],
    [{ text: '👤 Мой профиль', callback_data: 'profile:main' }],
    [{ text: '🔔 Мои уведомления', callback_data: 'settings:notifications' }]
  ];
  if (isStaff(role)) {
    rows.unshift([{ text: '➕ Создать публикацию', callback_data: 'broadcast:new' }]);
    rows.push([{ text: '📄 Мои публикации', callback_data: 'broadcast:mine' }]);
  }
  if (isAdmin(role)) {
    rows.push([{ text: '✅ На согласовании', callback_data: 'review:list' }]);
    rows.push([{ text: '📣 Чаты и каналы', callback_data: 'targets:list' }]);
    rows.push([{ text: '📊 Аналитика', callback_data: 'analytics:main' }]);
  }
  return { inline_keyboard: rows };
}

async function ensureUser(env, u) {
  const ownerId = env.OWNER_TELEGRAM_ID ? Number(env.OWNER_TELEGRAM_ID) : null;
  await env.DB.prepare(`INSERT INTO users (telegram_id, username, first_name, last_name, role)
    VALUES (?1, ?2, ?3, ?4, ?5)
    ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name,
      last_name=excluded.last_name, role=CASE WHEN ?6=1 THEN 'owner' ELSE users.role END, updated_at=CURRENT_TIMESTAMP`)
    .bind(u.id, u.username || null, u.first_name || null, u.last_name || null, ownerId === u.id ? 'owner' : 'viewer', ownerId === u.id ? 1 : 0).run();
  return env.DB.prepare('SELECT * FROM users WHERE telegram_id=?1').bind(u.id).first();
}

async function setState(env, telegramId, state, payload = {}) {
  await env.DB.prepare(`INSERT INTO user_states (telegram_id, state, payload_json)
    VALUES (?1, ?2, ?3)
    ON CONFLICT(telegram_id) DO UPDATE SET state=excluded.state, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP`)
    .bind(telegramId, state, JSON.stringify(payload)).run();
}
async function getState(env, telegramId) {
  const row = await env.DB.prepare('SELECT * FROM user_states WHERE telegram_id=?1').bind(telegramId).first();
  if (!row) return null;
  let payload = {};
  try { payload = JSON.parse(row.payload_json || '{}'); } catch {}
  return { state: row.state, payload };
}
async function clearState(env, telegramId) {
  await env.DB.prepare('DELETE FROM user_states WHERE telegram_id=?1').bind(telegramId).run();
}

function parseDateTime(input) {
  const m = String(input).trim().match(/^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})$/);
  if (!m) return null;
  const [, dd, mm, yyyy, hh, min] = m;
  const db = `${yyyy}-${mm}-${dd} ${hh}:${min}:00`;
  const d = new Date(`${yyyy}-${mm}-${dd}T${hh}:${min}:00+04:00`);
  return Number.isNaN(d.getTime()) ? null : { db, date: d };
}

function formatBroadcast(b, prefix = '') {
  let text = `${prefix ? prefix + '\n\n' : ''}<b>${esc(b.title)}</b>\n\n${esc(b.description)}`;
  text += `\n\n📅 ${esc(b.starts_at.replace('T',' ').replace(/:00$/, ''))}`;
  if (b.registration_url) text += `\n\n🔗 <a href="${esc(b.registration_url)}">Регистрация</a>`;
  return text;
}

async function logDelivery(env, broadcastId, reminderId, platform, destinationType, destinationId, status, errorText = null) {
  await env.DB.prepare(`INSERT INTO delivery_log
    (broadcast_id, reminder_id, platform, destination_type, destination_id, status, error_text)
    VALUES (?1,?2,?3,?4,?5,?6,?7)`)
    .bind(broadcastId, reminderId, platform, destinationType, destinationId, status, errorText).run();
}

async function sendBroadcastToTelegram(env, b, reminderId = null, prefix = '') {
  let sql = "SELECT * FROM chats WHERE status='approved' AND bot_can_post=1";
  const binds = [];
  if (b.network_scope !== 'both') { sql += ` AND network=?${binds.length + 1}`; binds.push(b.network_scope); }
  if (b.country_scope !== 'ALL') { sql += ` AND (country IS NULL OR country=?${binds.length + 1})`; binds.push(b.country_scope); }
  let stmt = env.DB.prepare(sql);
  if (binds.length) stmt = stmt.bind(...binds);
  const targets = await stmt.all();
  const text = formatBroadcast(b, prefix);

  for (const target of targets.results || []) {
    try {
      if (b.photo_file_id) await tg(env, 'sendPhoto', { chat_id: target.chat_id, photo: b.photo_file_id, caption: text, parse_mode: 'HTML' });
      else await tg(env, 'sendMessage', { chat_id: target.chat_id, text, parse_mode: 'HTML', disable_web_page_preview: false });
      await logDelivery(env, b.id, reminderId, 'telegram', 'chat', String(target.chat_id), 'sent');
    } catch (e) {
      await logDelivery(env, b.id, reminderId, 'telegram', 'chat', String(target.chat_id), 'failed', String(e.message).slice(0,500));
      await env.DB.prepare("UPDATE chats SET bot_can_post=0, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?1").bind(target.chat_id).run();
    }
  }

  if (Number(b.personal_scope) === 1) {
    let usql = "SELECT * FROM users WHERE notifications_enabled=1";
    const ub = [];
    if (b.country_scope !== 'ALL') { usql += ' AND country=?1'; ub.push(b.country_scope); }
    let ust = env.DB.prepare(usql);
    if (ub.length) ust = ust.bind(...ub);
    const users = await ust.all();
    for (const u of users.results || []) {
      try {
        if (b.photo_file_id) await tg(env, 'sendPhoto', { chat_id: u.telegram_id, photo: b.photo_file_id, caption: text, parse_mode: 'HTML' });
        else await tg(env, 'sendMessage', { chat_id: u.telegram_id, text, parse_mode: 'HTML' });
        await logDelivery(env, b.id, reminderId, 'telegram', 'user', String(u.telegram_id), 'sent');
      } catch (e) {
        await logDelivery(env, b.id, reminderId, 'telegram', 'user', String(u.telegram_id), 'failed', String(e.message).slice(0,500));
      }
    }
  }
}

async function sendWhatsAppTemplate(env, to, b) {
  if (env.WHATSAPP_ENABLED !== 'true') return false;
  if (!env.WHATSAPP_ACCESS_TOKEN || !env.WHATSAPP_PHONE_NUMBER_ID || !env.WHATSAPP_TEMPLATE_NAME) return false;
  const url = `${GRAPH}/${env.WHATSAPP_GRAPH_VERSION || 'v23.0'}/${env.WHATSAPP_PHONE_NUMBER_ID}/messages`;
  const payload = {
    messaging_product: 'whatsapp', to, type: 'template',
    template: {
      name: env.WHATSAPP_TEMPLATE_NAME,
      language: { code: env.WHATSAPP_TEMPLATE_LANG || 'ru' },
      components: [{ type: 'body', parameters: [
        { type: 'text', text: b.title },
        { type: 'text', text: b.starts_at },
        { type: 'text', text: b.registration_url || '-' }
      ]}]
    }
  };
  const r = await fetch(url, { method: 'POST', headers: { 'content-type':'application/json', authorization:`Bearer ${env.WHATSAPP_ACCESS_TOKEN}` }, body: JSON.stringify(payload) });
  if (!r.ok) throw new Error(`WhatsApp send failed: ${r.status}`);
  return true;
}

async function sendBroadcastToWhatsApp(env, b, reminderId = null) {
  if (Number(b.whatsapp_duplicate) !== 1 || env.WHATSAPP_ENABLED !== 'true') return;
  let sql = "SELECT * FROM users WHERE whatsapp_opt_in=1 AND phone IS NOT NULL AND phone<>''";
  const binds = [];
  if (b.country_scope !== 'ALL') { sql += ' AND country=?1'; binds.push(b.country_scope); }
  let stmt = env.DB.prepare(sql);
  if (binds.length) stmt = stmt.bind(...binds);
  const users = await stmt.all();
  for (const u of users.results || []) {
    try {
      const sent = await sendWhatsAppTemplate(env, u.phone, b);
      await logDelivery(env, b.id, reminderId, 'whatsapp', 'user', u.phone, sent ? 'sent' : 'skipped', sent ? null : 'WhatsApp connector disabled');
    } catch (e) {
      await logDelivery(env, b.id, reminderId, 'whatsapp', 'user', u.phone, 'failed', String(e.message).slice(0,500));
    }
  }
}

async function fanout(env, b, reminderId = null, prefix = '') {
  await sendBroadcastToTelegram(env, b, reminderId, prefix);
  await sendBroadcastToWhatsApp(env, b, reminderId);
}

async function scheduleReminders(env, b, offsets = [4320,1440,60]) {
  const start = new Date(`${b.starts_at.replace(' ', 'T')}+04:00`);
  for (const mins of offsets) {
    const when = new Date(start.getTime() - mins * 60000);
    if (when.getTime() <= Date.now()) continue;
    await env.DB.prepare('INSERT INTO reminders (broadcast_id, remind_at, offset_minutes) VALUES (?1, ?2, ?3)')
      .bind(b.id, when.toISOString().slice(0,19).replace('T',' '), mins).run();
  }
}

async function publishBroadcast(env, id, approverId) {
  const b = await env.DB.prepare('SELECT * FROM broadcasts WHERE id=?1').bind(id).first();
  if (!b || !['pending','approved'].includes(b.status)) return false;
  await env.DB.prepare("UPDATE broadcasts SET status='publishing', approved_by=?2, approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?1").bind(id, approverId).run();
  await fanout(env, b, null, '📢 Новая публикация');
  await scheduleReminders(env, b);
  await env.DB.prepare("UPDATE broadcasts SET status='published', published_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?1").bind(id).run();
  return true;
}

async function upsertTarget(env, chat, fromId = null) {
  if (!['group','supergroup','channel'].includes(chat.type)) return;
  await env.DB.prepare(`INSERT INTO chats (chat_id, title, username, chat_type, added_by, status, bot_can_post)
    VALUES (?1, ?2, ?3, ?4, ?5, 'pending', 1)
    ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, username=excluded.username, chat_type=excluded.chat_type,
      bot_can_post=1, status=CASE WHEN chats.status='disabled' THEN 'pending' ELSE chats.status END, updated_at=CURRENT_TIMESTAMP`)
    .bind(chat.id, chat.title || String(chat.id), chat.username || null, chat.type, fromId).run();
}

async function handleMyChatMember(env, update) {
  const chat = update.chat;
  const status = update.new_chat_member?.status;
  if (!['group','supergroup','channel'].includes(chat.type)) return;
  if (['administrator','member'].includes(status)) await upsertTarget(env, chat, update.from?.id || null);
  else if (['left','kicked'].includes(status)) await env.DB.prepare("UPDATE chats SET status='disabled', bot_can_post=0, updated_at=CURRENT_TIMESTAMP WHERE chat_id=?1").bind(chat.id).run();
}

async function handleStateInput(env, m, user, st) {
  const txt = m.text?.trim();
  if (st.state === 'profile:country') {
    if (!txt) return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Отправьте название страны текстом.'});
    await env.DB.prepare('UPDATE users SET country=?2, updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?1').bind(user.telegram_id, txt).run();
    await clearState(env,user.telegram_id);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:`✅ Страна сохранена: ${txt}`,reply_markup:mainMenu(user.role)});
  }
  if (st.state === 'profile:phone') {
    if (!txt || !/^\+?[1-9]\d{6,14}$/.test(txt.replace(/[\s()-]/g,''))) return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Отправьте номер в международном формате, например +374XXXXXXXX.'});
    const phone = txt.replace(/[\s()-]/g,'').replace(/^\+/, '');
    await env.DB.prepare('UPDATE users SET phone=?2, whatsapp_opt_in=1, updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?1').bind(user.telegram_id, phone).run();
    await clearState(env,user.telegram_id);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'✅ Номер сохранён для WhatsApp-уведомлений.',reply_markup:mainMenu(user.role)});
  }
  if (!st.state.startsWith('broadcast:') || !isStaff(user.role)) return;
  const p = st.payload;
  if (st.state === 'broadcast:title') {
    if (!txt) return; p.title = txt; await setState(env,user.telegram_id,'broadcast:description',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 2/7. Отправьте описание.'});
  }
  if (st.state === 'broadcast:description') {
    if (!txt) return; p.description = txt; await setState(env,user.telegram_id,'broadcast:photo',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 3/7. Отправьте афишу как фото или «-».'});
  }
  if (st.state === 'broadcast:photo') {
    if (m.photo?.length) p.photo_file_id = m.photo[m.photo.length-1].file_id;
    else if (txt === '-') p.photo_file_id = null;
    else return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Отправьте фото или «-».'});
    await setState(env,user.telegram_id,'broadcast:datetime',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 4/7. Дата и время: ДД.ММ.ГГГГ ЧЧ:ММ (по Еревану).'});
  }
  if (st.state === 'broadcast:datetime') {
    const dt = parseDateTime(txt); if (!dt) return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Пример: 15.10.2026 18:30'});
    p.starts_at = dt.db; await setState(env,user.telegram_id,'broadcast:registration',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 5/7. Ссылка регистрации или «-».'});
  }
  if (st.state === 'broadcast:registration') {
    p.registration_url = txt === '-' ? null : txt; await setState(env,user.telegram_id,'broadcast:country',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 6/7. Напишите ALL для всех стран или название страны.'});
  }
  if (st.state === 'broadcast:country') {
    p.country_scope = (txt || '').toUpperCase() === 'ALL' ? 'ALL' : txt; await setState(env,user.telegram_id,'broadcast:network',p);
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Шаг 7/7. Выберите сеть:',reply_markup:{inline_keyboard:[
      [{text:'Комиссия',callback_data:'draft:network:commission'},{text:'МДС',callback_data:'draft:network:mds'}],
      [{text:'Обе сети',callback_data:'draft:network:both'}]
    ]}});
  }
}

async function handlePrivateMessage(env, m) {
  const user = await ensureUser(env, m.from);
  if (m.text === '/start') return tg(env,'sendMessage',{chat_id:m.chat.id,text:`Информационный бот Комиссии по взаимодействию с молодёжью.${user.country ? `\nСтрана: ${user.country}` : '\n\nЗаполните профиль для личных рассылок по странам.'}`,reply_markup:mainMenu(user.role)});
  if (m.text === '/id') return tg(env,'sendMessage',{chat_id:m.chat.id,text:`Ваш Telegram ID: ${m.from.id}`});
  if (m.text === '/cancel') { await clearState(env,user.telegram_id); return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Действие отменено.',reply_markup:mainMenu(user.role)}); }
  if (m.text?.startsWith('/role ') && user.role === 'owner') {
    const [, id, role] = m.text.trim().split(/\s+/);
    if (!['viewer','editor','admin'].includes(role) || !/^\d+$/.test(id)) return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Формат: /role TELEGRAM_ID viewer|editor|admin'});
    await env.DB.prepare('UPDATE users SET role=?2, updated_at=CURRENT_TIMESTAMP WHERE telegram_id=?1').bind(Number(id),role).run();
    return tg(env,'sendMessage',{chat_id:m.chat.id,text:`✅ Роль ${role} назначена пользователю ${id}.`});
  }
  const st = await getState(env,user.telegram_id);
  if (st) return handleStateInput(env,m,user,st);
  return tg(env,'sendMessage',{chat_id:m.chat.id,text:'Выберите действие:',reply_markup:mainMenu(user.role)});
}

async function finishDraft(env, user, chatId, network, whatsapp) {
  const st = await getState(env,user.telegram_id); if (!st || st.state !== 'broadcast:network') return;
  const p = st.payload;
  const row = await env.DB.prepare(`INSERT INTO broadcasts
    (title,description,photo_file_id,starts_at,registration_url,country_scope,network_scope,personal_scope,whatsapp_duplicate,status,created_by)
    VALUES (?1,?2,?3,?4,?5,?6,?7,1,?8,'pending',?9) RETURNING id`)
    .bind(p.title,p.description,p.photo_file_id||null,p.starts_at,p.registration_url||null,p.country_scope||'ALL',network,whatsapp?1:0,user.telegram_id).first();
  await clearState(env,user.telegram_id);
  return tg(env,'sendMessage',{chat_id:chatId,text:`✅ Публикация #${row.id} отправлена руководителю на согласование.\n\nСтраны: ${p.country_scope}\nСеть: ${network}\nЛичные Telegram-рассылки: да\nWhatsApp: ${whatsapp?'да':'нет'}`,reply_markup:mainMenu(user.role)});
}

async function handleCallback(env, q) {
  const user = await ensureUser(env, q.from);
  await tg(env,'answerCallbackQuery',{callback_query_id:q.id});
  const chatId=q.message?.chat?.id; if(!chatId)return;
  const data=q.data||'';

  if(data==='profile:main') return tg(env,'sendMessage',{chat_id:chatId,text:`👤 Профиль\n\nСтрана: ${user.country||'не указана'}\nWhatsApp: ${user.phone?'+'+user.phone:'не подключён'}\nУведомления: ${user.notifications_enabled?'включены':'выключены'}`,reply_markup:{inline_keyboard:[[{text:'🌍 Указать страну',callback_data:'profile:country'}],[{text:'💬 Подключить WhatsApp',callback_data:'profile:phone'}]]}});
  if(data==='profile:country'){await setState(env,user.telegram_id,'profile:country',{});return tg(env,'sendMessage',{chat_id:chatId,text:'Напишите вашу страну.'});}
  if(data==='profile:phone'){await setState(env,user.telegram_id,'profile:phone',{});return tg(env,'sendMessage',{chat_id:chatId,text:'Отправьте номер WhatsApp в международном формате.'});}
  if(data==='settings:notifications'){const next=user.notifications_enabled?0:1;await env.DB.prepare('UPDATE users SET notifications_enabled=?2 WHERE telegram_id=?1').bind(user.telegram_id,next).run();return tg(env,'sendMessage',{chat_id:chatId,text:`🔔 Личные уведомления ${next?'включены':'выключены'}.`});}

  if(data==='broadcast:new'&&isStaff(user.role)){await setState(env,user.telegram_id,'broadcast:title',{});return tg(env,'sendMessage',{chat_id:chatId,text:'Шаг 1/7. Отправьте название публикации.\n/cancel — отменить'});}
  if(data.startsWith('draft:network:')&&isStaff(user.role)){const network=data.split(':')[2];return tg(env,'sendMessage',{chat_id:chatId,text:'Дублировать рассылку в WhatsApp зарегистрированным пользователям?',reply_markup:{inline_keyboard:[[{text:'Да',callback_data:`draft:wa:1:${network}`}],[{text:'Нет',callback_data:`draft:wa:0:${network}`}]]}});}
  if(data.startsWith('draft:wa:')&&isStaff(user.role)){const p=data.split(':');return finishDraft(env,user,chatId,p[3],p[2]==='1');}

  if(data==='review:list'&&isAdmin(user.role)){
    const rows=await env.DB.prepare("SELECT id,title FROM broadcasts WHERE status='pending' ORDER BY created_at LIMIT 20").all();
    if(!(rows.results||[]).length)return tg(env,'sendMessage',{chat_id:chatId,text:'Нет публикаций на согласовании.'});
    return tg(env,'sendMessage',{chat_id:chatId,text:'✅ На согласовании:',reply_markup:{inline_keyboard:rows.results.map(b=>[{text:`#${b.id} ${b.title}`.slice(0,55),callback_data:`review:view:${b.id}`}])}});
  }
  if(data.startsWith('review:view:')&&isAdmin(user.role)){
    const id=Number(data.split(':')[2]);const b=await env.DB.prepare('SELECT * FROM broadcasts WHERE id=?1').bind(id).first();if(!b)return;
    return tg(env,'sendMessage',{chat_id:chatId,text:`${formatBroadcast(b)}\n\n🌍 ${esc(b.country_scope)}\n📡 ${esc(b.network_scope)}\n🔔 За 3 дня, сутки и час\n💬 WhatsApp: ${b.whatsapp_duplicate?'да':'нет'}`,parse_mode:'HTML',reply_markup:{inline_keyboard:[[{text:'✅ Одобрить и опубликовать',callback_data:`review:approve:${id}`}],[{text:'❌ Отклонить',callback_data:`review:reject:${id}`}]]}});
  }
  if(data.startsWith('review:approve:')&&isAdmin(user.role)){const id=Number(data.split(':')[2]);const ok=await publishBroadcast(env,id,user.telegram_id);return tg(env,'sendMessage',{chat_id:chatId,text:ok?'✅ Опубликовано. Напоминания запланированы.':'Уже обработано.'});}
  if(data.startsWith('review:reject:')&&isAdmin(user.role)){const id=Number(data.split(':')[2]);await env.DB.prepare("UPDATE broadcasts SET status='rejected', approved_by=?2 WHERE id=?1 AND status='pending'").bind(id,user.telegram_id).run();return tg(env,'sendMessage',{chat_id:chatId,text:`❌ #${id} отклонена.`});}

  if(data==='targets:list'&&isAdmin(user.role)){
    const rows=await env.DB.prepare("SELECT * FROM chats WHERE status IN ('pending','approved') ORDER BY status DESC,title LIMIT 30").all();
    if(!(rows.results||[]).length)return tg(env,'sendMessage',{chat_id:chatId,text:'Подключённых чатов и каналов пока нет.'});
    return tg(env,'sendMessage',{chat_id:chatId,text:'📣 Чаты и каналы:',reply_markup:{inline_keyboard:rows.results.map(t=>[{text:`${t.status==='approved'?'✅':'⏳'}${t.chat_type==='channel'?'📢':'💬'} ${t.title}`.slice(0,55),callback_data:`target:view:${t.chat_id}`}])}});
  }
  if(data.startsWith('target:view:')&&isAdmin(user.role)){
    const id=data.slice('target:view:'.length);const t=await env.DB.prepare('SELECT * FROM chats WHERE chat_id=?1').bind(id).first();if(!t)return;
    return tg(env,'sendMessage',{chat_id:chatId,text:`${t.chat_type==='channel'?'📢 Канал':'💬 Чат'}: ${t.title}\nСтатус: ${t.status}\nСеть: ${t.network}\nСтрана: ${t.country||'не задана'}`,reply_markup:{inline_keyboard:[[{text:'✅ Комиссия',callback_data:`target:approve:commission:${t.chat_id}`}],[{text:'✅ МДС',callback_data:`target:approve:mds:${t.chat_id}`}],[{text:'🚫 Отключить',callback_data:`target:disable:${t.chat_id}`}]]}});
  }
  if(data.startsWith('target:approve:')&&isAdmin(user.role)){const p=data.split(':');await env.DB.prepare("UPDATE chats SET status='approved',network=?2,approved_by=?3,approved_at=CURRENT_TIMESTAMP,bot_can_post=1 WHERE chat_id=?1").bind(p[3],p[2],user.telegram_id).run();return tg(env,'sendMessage',{chat_id:chatId,text:'✅ Точка рассылки подключена.'});}
  if(data.startsWith('target:disable:')&&isAdmin(user.role)){const id=data.slice('target:disable:'.length);await env.DB.prepare("UPDATE chats SET status='disabled',bot_can_post=0 WHERE chat_id=?1").bind(id).run();return tg(env,'sendMessage',{chat_id:chatId,text:'🚫 Отключено.'});}

  if(data==='events:list'){
    const rows=await env.DB.prepare("SELECT id,title,starts_at FROM broadcasts WHERE status='published' AND starts_at>=CURRENT_TIMESTAMP ORDER BY starts_at LIMIT 10").all();
    return tg(env,'sendMessage',{chat_id:chatId,text:(rows.results||[]).length?'📅 Ближайшие события:\n\n'+rows.results.map(x=>`#${x.id} ${x.title}\n${x.starts_at}`).join('\n\n'):'Ближайших событий пока нет.'});
  }
  if(data==='broadcast:mine'&&isStaff(user.role)){
    const rows=await env.DB.prepare('SELECT id,title,status,starts_at FROM broadcasts WHERE created_by=?1 ORDER BY created_at DESC LIMIT 10').bind(user.telegram_id).all();
    return tg(env,'sendMessage',{chat_id:chatId,text:(rows.results||[]).length?'📄 Мои публикации:\n\n'+rows.results.map(x=>`#${x.id} ${x.title}\n${x.status} • ${x.starts_at}`).join('\n\n'):'Пока нет публикаций.'});
  }
  if(data==='analytics:main'&&isAdmin(user.role)){
    const chats=await env.DB.prepare("SELECT COUNT(*) c FROM chats WHERE status='approved'").first();
    const users=await env.DB.prepare('SELECT COUNT(*) c FROM users').first();
    const pending=await env.DB.prepare("SELECT COUNT(*) c FROM broadcasts WHERE status='pending'").first();
    const published=await env.DB.prepare("SELECT COUNT(*) c FROM broadcasts WHERE status='published'").first();
    const sent=await env.DB.prepare("SELECT COUNT(*) c FROM delivery_log WHERE status='sent'").first();
    return tg(env,'sendMessage',{chat_id:chatId,text:`📊 Аналитика\n\nПользователей: ${users?.c||0}\nЧатов/каналов: ${chats?.c||0}\nНа согласовании: ${pending?.c||0}\nОпубликовано: ${published?.c||0}\nУспешных доставок: ${sent?.c||0}`});
  }
}

async function processUpdate(env, update) {
  if(update.my_chat_member)return handleMyChatMember(env,update.my_chat_member);
  if(update.callback_query)return handleCallback(env,update.callback_query);
  if(update.message&&update.message.chat.type==='private')return handlePrivateMessage(env,update.message);
  if(update.message&&['group','supergroup'].includes(update.message.chat.type))return upsertTarget(env,update.message.chat,update.message.from?.id||null);
  if(update.channel_post?.chat?.type==='channel')return upsertTarget(env,update.channel_post.chat,null);
}

export default {
  async fetch(request, env) {
    const url=new URL(request.url);
    if(url.pathname==='/health')return new Response('ok');
    if(request.method!=='POST')return new Response('Commission Youth Information Bot');
    const update=await request.json();await processUpdate(env,update);return new Response('ok');
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async()=>{
      const due=await env.DB.prepare("SELECT r.id reminder_id,r.offset_minutes,b.* FROM reminders r JOIN broadcasts b ON b.id=r.broadcast_id WHERE r.status='scheduled' AND r.remind_at<=CURRENT_TIMESTAMP AND b.status='published' ORDER BY r.remind_at LIMIT 25").all();
      for(const r of due.results||[]){
        await env.DB.prepare("UPDATE reminders SET status='sending' WHERE id=?1 AND status='scheduled'").bind(r.reminder_id).run();
        try{
          const label=r.offset_minutes>=1440?`🔔 Напоминание: до начала ${Math.round(r.offset_minutes/1440)} дн.`:`🔔 Напоминание: до начала ${Math.round(r.offset_minutes/60)} ч.`;
          await fanout(env,r,r.reminder_id,label);
          await env.DB.prepare("UPDATE reminders SET status='sent',sent_at=CURRENT_TIMESTAMP WHERE id=?1").bind(r.reminder_id).run();
        }catch(e){await env.DB.prepare("UPDATE reminders SET status='failed' WHERE id=?1").bind(r.reminder_id).run();}
      }
    })());
  }
};
