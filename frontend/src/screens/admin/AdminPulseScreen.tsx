import {useState} from 'react';
import {fetchPulseCycles,fetchPulseSchedule,fetchPulseArchive,downloadPulseArchive,pulseWrite,describeActionError,type PulseSchedule,fetchPulseQuestions,type PulseQuestion} from '../../api/client';
import {useAsync} from '../../hooks/useAsync';
import {Card} from '../../components/Card';
const days=['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'];
export function AdminPulseScreen(){
 const [refresh,setRefresh]=useState(0),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [schedule,setSchedule]=useState<PulseSchedule|null>(null);
 const [snapshot,setSnapshot]=useState<Record<string,unknown>|null>(null);
 const templates=useAsync(()=>fetchPulseQuestions(),[refresh]);
 const [edited,setEdited]=useState<PulseQuestion[]|null>(null);
 const qs=edited ?? (templates.status==='ready'?templates.data:[]);
 const cycles=useAsync(()=>fetchPulseCycles(),[refresh]);
 const config=useAsync(()=>fetchPulseSchedule(),[refresh]);
 const current=schedule ?? (config.status==='ready'?config.data:null);
 async function run(action:()=>Promise<void>){setBusy(true);setError('');try{await action();setRefresh(x=>x+1);}catch(e){setError(describeActionError(e));}finally{setBusy(false);}}
 async function download(id:number,format:'docx'|'pdf',week:number){const blob=await downloadPulseArchive(id,format);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`ERA_PULSE_W${week}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
 return <div style={{display:'grid',gap:'1rem'}}>
 <p>Итоги недели, расписание и архив отчётов. Личные ответы доступны администрации.</p>
 {error&&<p role="alert">{error}</p>}
 {current&&<Card><h2>Расписание</h2><p>Часовой пояс: {current.timezone}</p>
 <label><input type="checkbox" checked={current.enabled} onChange={e=>setSchedule({...current,enabled:e.target.checked})}/> Сбор включён</label>
 <p><label>Открытие <select value={current.open_weekday} onChange={e=>setSchedule({...current,open_weekday:Number(e.target.value)})}>{days.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></label></p>
 <label>Время <input type="time" value={current.open_time.slice(0,5)} onChange={e=>setSchedule({...current,open_time:e.target.value})}/></label>
 {([['deadline_hours','Длительность сбора, часов'],['first_reminder_hours','Первое напоминание: часов до срока'],['final_reminder_hours','Последнее напоминание: часов до срока']] as const).map(([key,label])=><p key={key}><label>{label} <input type="number" min={1} max={168} value={current[key]} onChange={e=>setSchedule({...current,[key]:Number(e.target.value)})}/></label></p>)}
 <label>День итогов <select value={current.report_weekday} onChange={e=>setSchedule({...current,report_weekday:Number(e.target.value)})}>{days.map((d,i)=><option key={d} value={i}>{d}</option>)}</select></label>
 <p>Изменения применяются к новым неделям. Первое напоминание должно быть раньше последнего, оба — до срока.</p>
 <button disabled={busy} onClick={()=>run(async()=>{await pulseWrite('schedule','PUT',current);setSchedule(null);})}>Сохранить расписание</button></Card>}
 <Card><h2>Вопросы</h2><p>Изменения применяются к новым формам. Уже начатые ответы сохраняют прежние вопросы.</p>{qs.map((q,i)=><div key={q.key} style={{marginBottom:12}}><label>Вопрос {i+1}<textarea value={q.text} maxLength={300} onChange={e=>setEdited(qs.map((x,j)=>j===i?{...x,text:e.target.value}:x))}/></label><label><input type="checkbox" checked={q.required} onChange={e=>setEdited(qs.map((x,j)=>j===i?{...x,required:e.target.checked}:x))}/> Обязательный</label><label> Для кого <select value={q.audience??"all"} onChange={e=>setEdited(qs.map((x,j)=>j===i?{...x,audience:e.target.value}:x))}>{[["all","Все"],["chairman","Председатель"],["head","Руководители"],["external","Внешние связи"],["internal","Внутренние дела"],["media","Медиа"]].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label><label><input type="checkbox" checked={q.is_active!==false} onChange={e=>setEdited(qs.map((x,j)=>j===i?{...x,is_active:e.target.checked}:x))}/> Включён</label><button disabled={busy||i===0} onClick={()=>{const next=[...qs];[next[i-1],next[i]]=[next[i],next[i-1]];setEdited(next);}}>Выше</button><button disabled={busy||qs.length===1} onClick={()=>setEdited(qs.filter((_,j)=>i!==j))}>Удалить</button></div>)}<button disabled={busy||qs.length>=40} onClick={()=>setEdited([...qs,{key:`question_${Date.now()}`,text:'Новый вопрос',required:false}])}>Добавить вопрос</button><button disabled={busy||!edited} onClick={()=>run(async()=>{await pulseWrite('questions','PUT',{questions:qs});setEdited(null);})}>Сохранить вопросы</button></Card>
 <h2>Недели и архив</h2>
 {cycles.status==='loading'&&<p>Загрузка…</p>}{cycles.status==='error'&&<p>Не удалось загрузить недели.</p>}
 {cycles.status==='ready'&&cycles.data.map(c=><Card key={c.id}><h3>W{c.week_number} · {c.date_from} — {c.date_to}</h3><p>Ответили {c.submitted_count} / {c.eligible_count}</p>
 {c.archive_id?<div style={{display:'flex',gap:8,flexWrap:'wrap'}}>{(['docx','pdf'] as const).map(f=><button disabled={busy} key={f} onClick={()=>run(()=>download(c.archive_id!,f,c.week_number))}>{f.toUpperCase()}</button>)}<button disabled={busy} onClick={()=>run(async()=>setSnapshot((await fetchPulseArchive(c.archive_id!)).snapshot))}>Источники и полный состав</button></div>:<button disabled={busy||Date.now()<Date.parse(c.deadline_at)} onClick={()=>run(()=>pulseWrite(`cycles/${c.id}/archive`,'POST'))}>Сформировать отчёт после срока</button>}
 </Card>)}
 {cycles.status==='ready'&&!cycles.data.length&&<p>Недели появятся после привязки чата ЛИДЕРЫ.</p>}
 {snapshot&&<Card><h3>Данные выбранной недели</h3><p>Период: {String(snapshot.period)}<br/>Зафиксировано: {String(snapshot.frozen_at)}</p>{(['reports','tasks','blockers','events'] as const).map(key=><section key={key}><h4>{{reports:'Ответы команды',tasks:'Завершённые задачи',blockers:'Блокеры',events:'Мероприятия'}[key]}</h4>{(snapshot[key] as Record<string,unknown>[] ?? []).map((row,i)=><p key={i}>#{String(row.id)} · {String(row.title ?? row.result ?? '')}{row.text ? ' — '+String(row.text):''}{row.blocker ? ' · Требует решения: '+String(row.blocker):''}{Array.isArray(row.priorities)&&row.priorities.length ? ' · Планы: '+row.priorities.join('; '):''}</p>)}</section>)}{(snapshot.warnings as string[] ?? []).map(w=><p key={w}>{w}</p>)}<button onClick={()=>setSnapshot(null)}>Закрыть</button></Card>}
 </div>
}
