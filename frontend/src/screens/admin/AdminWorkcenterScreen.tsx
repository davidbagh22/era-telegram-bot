import {useRef, useState} from 'react';
import {fetchWorkTasks, fetchWorkRoster, fetchWorkDecisions, fetchWorkScopes, fetchWorkTeam,
  fetchWorkCampaigns, workWrite, describeActionError, type WorkTask, type WorkPerson, type WorkScope} from '../../api/client';
import {useAsync} from '../../hooks/useAsync';
import {Card} from '../../components/Card';
import {AdminPulseScreen} from './AdminPulseScreen';

const labels:Record<string,string>={new:'Предложена',published:'Доступна',in_progress:'В работе',review:'На проверке',completed:'Выполнена',cancelled:'Отменена',overdue:'Просрочена'};
const roles:Record<string,string>={participant:'Участник',activist:'Активист',leader:'Лидер',head:'Руководитель',council:'Совет',admin:'Администратор'};
const campaignLabels:Record<string,string>={sending:'Отправляется',paused:'На паузе',sent:'Передано Telegram',cancelled:'Отменена',partial:'Часть адресатов недоступна',review_required:'Нужна сверка доставки'};
const inputStyle={width:'100%',minWidth:0,boxSizing:'border-box' as const};
function scopePayload(scopes:WorkScope[], key:string){
 const scope=scopes.find(s=>`${s.kind}:${s.id}`===key)??scopes[0];
 return {department_id:scope?.kind==='department'?scope.id:null,direction_id:scope?.kind==='direction'?scope.id:null};
}

export function AdminWorkcenterScreen(){
 const [tab,setTab]=useState('tasks'),[refresh,setRefresh]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const [filter,setFilter]=useState('active'),[showForm,setShowForm]=useState(false),[title,setTitle]=useState(''),[description,setDescription]=useState('');
 const [assignee,setAssignee]=useState(''),[deadline,setDeadline]=useState(''),[scope,setScope]=useState(''),[points,setPoints]=useState(10),[urgent,setUrgent]=useState(false),[taskPreview,setTaskPreview]=useState(false);
 const [selected,setSelected]=useState<WorkTask|null>(null),[comment,setComment]=useState(''),[target,setTarget]=useState(''),[newDeadline,setNewDeadline]=useState('');
 const tasks=useAsync(fetchWorkTasks,[refresh]),roster=useAsync(fetchWorkRoster,[refresh]),decisions=useAsync(fetchWorkDecisions,[refresh]),scopes=useAsync(fetchWorkScopes,[refresh]);
 const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(0),[candidates,setCandidates]=useState(false);
 const team=useAsync(()=>fetchWorkTeam(search,page,candidates),[search,page,candidates,refresh]);
 const [person,setPerson]=useState<WorkPerson|null>(null);
 const [body,setBody]=useState(''),[broadcastScope,setBroadcastScope]=useState(''),[mode,setMode]=useState('group'),[acknowledge,setAcknowledge]=useState(true);
 const [broadcastPreview,setBroadcastPreview]=useState<number|null>(null);
 const campaigns=useAsync(fetchWorkCampaigns,[refresh]);
 const taskKey=useRef<{signature:string;key:string}|null>(null),campaignKey=useRef<{signature:string;key:string}|null>(null);
 const people=roster.status==='ready'?roster.data:[];
 const taskScopes=scopes.status==='ready'?scopes.data.tasks:[];
 const broadcastScopes=scopes.status==='ready'?scopes.data.broadcasts:[];
 const all=tasks.status==='ready'?tasks.data:[];
 const list=all.filter(t=>filter==='all'||filter==='active'&&!['completed','cancelled'].includes(t.status)||filter==='free'&&t.assignee_id===null&&!['completed','cancelled'].includes(t.status)||filter==='blocker'&&!!t.blocker||filter==='overdue'&&!!t.deadline&&Date.parse(t.deadline)<Date.now()&&!['completed','cancelled'].includes(t.status)||t.status===filter);
 async function run(f:()=>Promise<unknown>){setBusy(true);setError('');setNotice('');try{await f();setRefresh(x=>x+1);}catch(e){setError(describeActionError(e));}finally{setBusy(false);}}
 async function action(action:string,extra:Record<string,unknown>={}){if(!selected)return;await run(async()=>{const next=await workWrite(`tasks/${selected.id}/action`,{action,...extra});setSelected(next);});}
 function keyFor(ref:typeof taskKey,payload:unknown){const signature=JSON.stringify(payload);if(ref.current?.signature!==signature)ref.current={signature,key:crypto.randomUUID()};return ref.current.key;}
 function broadcastPayload(){const scoped=scopePayload(broadcastScopes,broadcastScope);return {body,mode:scoped.department_id||scoped.direction_id?'dm':mode,acknowledge,...scoped};}
 return <div style={{display:'grid',gap:16,minWidth:0}}>
  <p>Лидеры ЭРА: состав команды, рабочие задачи, сообщения и итоги недели.</p>
  <div role="tablist" aria-label="Лидеры" style={{display:'flex',gap:8,flexWrap:'wrap'}}>
   {[['team','Команда'],['tasks','Задачи'],['broadcasts','Рассылки'],['pulse','Пульс']].map(([value,label])=><button key={value} role="tab" aria-selected={tab===value} onClick={()=>{setTab(value);setError('');setNotice('');}}>{label}</button>)}
  </div>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {tab==='team'&&<>
   <p>Должность и статус лидера учитываются отдельно. Назначение лидером сохраняет историю и не выдаёт административные права.</p>
   <label>Поиск участника<input style={inputStyle} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Имя, фамилия или @имя_пользователя"/></label>
   <div><button disabled={busy} onClick={()=>{setSearch(query);setCandidates(true);setPage(0);}}>Найти / назначить лидера</button><button onClick={()=>{setSearch('');setQuery('');setCandidates(false);setPage(0);}}>Состав команды</button></div>
   {team.status==='loading'&&<p>Загружаем команду…</p>}{team.status==='error'&&<p role="alert">Не удалось загрузить команду. Попробуйте обновить.</p>}
   {team.status==='ready'&&team.data.items.length===0&&<p>Участники не найдены.</p>}
   {team.status==='ready'&&team.data.items.map(p=><Card key={p.id}><strong>{p.name}</strong><p>{roles[p.role]??p.role}</p><p>{p.offices.join(' · ')||'Должность не назначена'}</p>{p.can_set_leader&&<button onClick={()=>setPerson(p)}>{p.role==='leader'?'Снять статус лидера':'Назначить лидером'}</button>}</Card>)}
   <div>{page>0&&<button onClick={()=>setPage(p=>p-1)}>← Назад</button>}{team.status==='ready'&&team.data.has_more&&<button onClick={()=>setPage(p=>p+1)}>Далее →</button>}</div>
   {person&&<Card><h3>Подтвердите изменение</h3><p>{person.name}: {roles[person.role]} → {person.role==='leader'?'Активист':'Лидер'}</p><p>Баллы и результаты сохранятся. Руководящие должности и разрешения этим действием не меняются.</p><button disabled={busy} onClick={()=>run(async()=>{await workWrite(`team/${person.id}/leader`,{enabled:person.role!=='leader',expected_role:person.role});setPerson(null);setNotice('Статус обновлён.');})}>Подтвердить</button><button disabled={busy} onClick={()=>setPerson(null)}>Отмена</button></Card>}
  </>}
  {tab==='tasks'&&<>
   <button onClick={()=>{setShowForm(v=>!v);setTaskPreview(false);}}>➕ Новая задача</button>
   {showForm&&<Card><h2>Новая задача</h2>
    <label>Что сделать<input style={inputStyle} value={title} maxLength={255} onChange={e=>{setTitle(e.target.value);setTaskPreview(false);}}/></label>
    <label>Зачем и какой результат нужен<textarea style={inputStyle} value={description} maxLength={5000} onChange={e=>{setDescription(e.target.value);setTaskPreview(false);}}/></label>
    <label>Команда<select style={inputStyle} value={scope||`${taskScopes[0]?.kind}:${taskScopes[0]?.id}`} onChange={e=>{setScope(e.target.value);setAssignee('');setTaskPreview(false);}}>{taskScopes.map(s=><option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>{s.name}</option>)}</select></label>
    <label>Кому<select style={inputStyle} value={assignee} onChange={e=>{setAssignee(e.target.value);setTaskPreview(false);}}><option value="">Свободная задача: участник берёт сам</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
    <label>Срок по времени Вашего устройства<input style={inputStyle} type="datetime-local" value={deadline} onChange={e=>{setDeadline(e.target.value);setTaskPreview(false);}}/></label>
    <details><summary>Дополнительно</summary><label>Баллы после приёмки<input type="number" min={0} max={1000} value={points} onChange={e=>{setPoints(Number(e.target.value));setTaskPreview(false);}}/></label><label><input type="checkbox" checked={urgent} onChange={e=>{setUrgent(e.target.checked);setTaskPreview(false);}}/>Срочно</label></details>
    {!taskPreview?<button disabled={!title.trim()||busy||taskScopes.length===0} onClick={()=>setTaskPreview(true)}>Предпросмотр</button>:<><h3>{title}</h3><p style={{whiteSpace:'pre-wrap'}}>{description}</p><p>{people.find(p=>String(p.id)===assignee)?.name||'Свободная задача'} · {deadline?new Date(deadline).toLocaleString('ru-RU'):'Без срока'}</p><p>Баллы: {points}, только после приёмки другим руководителем.</p><button disabled={busy} onClick={()=>run(async()=>{const payload={title,description,assignee_id:assignee?Number(assignee):null,deadline:deadline?new Date(deadline).toISOString():null,priority:urgent?'urgent':'normal',points,...scopePayload(taskScopes,scope)};await workWrite('tasks',{...payload,request_key:keyFor(taskKey,payload)});setShowForm(false);setTaskPreview(false);setTitle('');setDescription('');setAssignee('');setDeadline('');setNotice('Задача сохранена. Состояние публикации видно в её карточке.');})}>Создать задачу</button></>}
   </Card>}
   <label>Показать<select style={inputStyle} value={filter} onChange={e=>setFilter(e.target.value)}>{[['active','Активные'],['free','Свободные'],['review','На проверке'],['overdue','Просроченные'],['blocker','Нужна помощь'],['completed','Выполненные'],['all','Все']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
   {tasks.status==='loading'&&<p>Загружаем задачи…</p>}{tasks.status==='error'&&<p role="alert">Не удалось загрузить задачи.</p>}{tasks.status==='ready'&&list.length===0&&<p>В этом списке пока нет задач.</p>}
   {list.map(t=><Card key={t.id}><strong>{t.title}</strong><p>{t.assignee_name} · {t.blocker?'Нужна помощь':t.assignee_id===null?'Свободна':labels[t.status]??t.status}</p><p>{t.deadline?new Date(t.deadline).toLocaleString('ru-RU'):'Без срока'}</p>{t.delivery_status!=='sent'&&<p>Карточка ожидает публикации в чате.</p>}<button onClick={()=>{setSelected(t);setTarget(t.assignee_id?String(t.assignee_id):'');setComment('');setNewDeadline('');}}>Открыть</button></Card>)}
   {selected&&<Card><h3>{selected.title}</h3><p style={{whiteSpace:'pre-wrap'}}>{selected.description}</p>{selected.telegram_url&&<a href={selected.telegram_url} target="_blank" rel="noreferrer">Карточка в чате лидеров</a>}
    {selected.submissions.map(s=><p key={s.id}>{s.text||'Результат с вложением'}{s.has_file?' · Файл доступен через «Подробнее» в Telegram':''}{s.comment?' · '+s.comment:''}</p>)}
    <label>Комментарий<textarea style={inputStyle} value={comment} onChange={e=>setComment(e.target.value)}/></label>
    {selected.status==='review'&&<><button disabled={busy} onClick={()=>action('accept')}>Принять</button><button disabled={busy||!comment.trim()} onClick={()=>action('return',{comment})}>Вернуть с комментарием</button></>}
    {!['completed','cancelled'].includes(selected.status)&&<details><summary>Изменить задачу</summary><label>Исполнитель<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Свободна</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><button disabled={busy} onClick={()=>action('assign',{assignee_id:target?Number(target):null})}>Передать</button><input aria-label="Новый срок" style={inputStyle} type="datetime-local" value={newDeadline} onChange={e=>setNewDeadline(e.target.value)}/><button disabled={busy} onClick={()=>action('deadline',{deadline:newDeadline?new Date(newDeadline).toISOString():null})}>{newDeadline?'Изменить срок':'Убрать срок'}</button><button disabled={busy} onClick={()=>action('urgent',{urgent:selected.priority!=='urgent'})}>{selected.priority==='urgent'?'Обычный приоритет':'Сделать срочной'}</button><button disabled={busy} onClick={()=>{if(window.confirm('Отменить задачу?'))void action('cancel');}}>Отменить задачу</button></details>}
    <details><summary>История</summary>{selected.history.map((h,i)=><p key={i}>{new Date(h.at).toLocaleString('ru-RU')} · {h.action.split('.').pop()}</p>)}</details><button onClick={()=>setSelected(null)}>Закрыть карточку</button>
   </Card>}
  </>}
  {tab==='broadcasts'&&<>
   <Card><h2>Сообщение команде</h2><label>Текст<textarea style={inputStyle} value={body} maxLength={2800} onChange={e=>{setBody(e.target.value);setBroadcastPreview(null);}}/></label>
    <label>Команда<select style={inputStyle} value={broadcastScope||`${broadcastScopes[0]?.kind}:${broadcastScopes[0]?.id}`} onChange={e=>{setBroadcastScope(e.target.value);setBroadcastPreview(null);}}>{broadcastScopes.map(s=><option key={`${s.kind}:${s.id}`} value={`${s.kind}:${s.id}`}>{s.name}</option>)}</select></label>
    <label>Доставка<select style={inputStyle} value={mode} onChange={e=>{setMode(e.target.value);setBroadcastPreview(null);}}><option value="group">В чат лидеров</option><option value="dm">Лично</option><option value="both">В чат и лично</option></select></label><p>Сообщения отдельному направлению доставляются только лично.</p>
    <label><input type="checkbox" checked={acknowledge} onChange={e=>{setAcknowledge(e.target.checked);setBroadcastPreview(null);}}/>Кнопка «Ознакомился»</label>
    {broadcastPreview===null?<button disabled={busy||!body.trim()||broadcastScopes.length===0} onClick={()=>run(async()=>{const payload=broadcastPayload();const r=await workWrite('campaigns/preview',{...payload,request_key:keyFor(campaignKey,payload)});setBroadcastPreview(r.recipients);})}>Предпросмотр</button>:<><p style={{whiteSpace:'pre-wrap'}}>{body}</p><p>Известных доступных аккаунтов: {broadcastPreview}. Доставка и ознакомление учитываются отдельно.</p><button disabled={busy} onClick={()=>run(async()=>{const payload=broadcastPayload();const r=await workWrite('campaigns',{...payload,request_key:keyFor(campaignKey,payload)});setNotice(`Рассылка №${r.id}: ${campaignLabels[r.status]??r.status}.`);setBroadcastPreview(null);setBody('');})}>Подтвердить отправку</button></>}
   </Card>
   {campaigns.status==='error'&&<p>Не удалось загрузить историю рассылок.</p>}{campaigns.status==='ready'&&campaigns.data.map(c=><Card key={c.id}><strong>№{c.id} · {campaignLabels[c.status]??c.status}</strong><p style={{whiteSpace:'pre-wrap'}}>{c.text}</p><p>Аккаунтов: {c.recipients} · Отправок: {c.sent} · Ознакомились: {c.read}</p>{!!c.uncertain&&<p>Нужна сверка: {c.uncertain}</p>}{!!c.unreachable&&<p>Недоступны: {c.unreachable}</p>}{(c.status==='sending'||c.status==='paused')&&<><button disabled={busy} onClick={()=>run(()=>workWrite(`campaigns/${c.id}/action`,{action:c.status==='paused'?'resume':'pause'}))}>{c.status==='paused'?'Продолжить':'Пауза'}</button><button disabled={busy} onClick={()=>{if(window.confirm('Отменить оставшиеся отправки?'))void run(()=>workWrite(`campaigns/${c.id}/action`,{action:'cancel'}));}}>Отменить оставшиеся</button></>}</Card>)}
  </>}
  {tab==='pulse'&&<><AdminPulseScreen/>
   <details><summary>Требует решения</summary>{decisions.status==='ready'&&decisions.data.filter(d=>d.status!=='resolved').map(d=><Card key={d.id}><p>{d.text}</p><label>Решение<textarea style={inputStyle} value={comment} onChange={e=>setComment(e.target.value)}/></label><label>Ответственный<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Не выбран</option>{people.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>{[['in_progress','В работу'],['resolved','Решено'],['deferred','Отложить']].map(([v,l])=><button disabled={busy} key={v} onClick={()=>run(()=>workWrite(`decisions/${d.id}`,{status:v,comment,responsible_id:target?Number(target):null}))}>{l}</button>)}</Card>)}</details>
  </>}
  <button disabled={busy} onClick={()=>setRefresh(v=>v+1)}>Обновить</button>
 </div>;
}
