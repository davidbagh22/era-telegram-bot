from __future__ import annotations
import json
from datetime import datetime, timezone
from sqlalchemy import select
from app.database.models import AppSetting, User, Office, UserOffice, LeadershipReport, LeadershipAttentionItem
from app.database.leadership_models import WeeklyPulseCycle, WeeklyPulseParticipant
from app.services import leadership_weekly_service


def question(key,text,required=False,audience='all',choices=None):
    return {'key':key,'text':text,'required':required,'audience':audience,'is_active':True,'choices':choices or [],'condition_key':None,'condition_value':None}


DEFAULT_QUESTIONS=[
 question('done','Что сделано за неделю сверх учтённых задач? Можно выбрать «Всё учтено» или «Не было активности».',True,choices=['Всё учтено','Не было активности']),
 question('result','Какой конкретный результат это дало?',True),
 question('projects','Какие проекты продвинулись? Укажи проект, статус и следующий шаг.'),
 question('blocker','Что мешает двигаться дальше? Если ничего — выбери «Нет».',False,choices=['Нет','Нужен человек','Нужна информация','Нужен ресурс','Нужно решение руководства']),
 question('plans','Какие три результата планируешь на следующую неделю? Каждый пункт с новой строки.',True),
 question('contacts','Есть новая возможность, контакт или встреча? Добавь организацию, результат, срок и ссылку.'),
 question('decision','Какой вопрос нужно решить Давиду / руководству? Если нет — пропусти.'),
 question('media','Есть результат для публикации? Добавь описание и фото / ссылку / документ.'),
 question('load','Какова загрузка на следующую неделю?',True,choices=['Есть свободный ресурс','Нормально','Высокая','Не могу брать задачи']),
 question('team','Состояние команды: результаты, кто проявил себя, кому нужна помощь и чего не хватает.',False,audience='head'),
 question('external','Внешние связи: организации, встречи, договорённости, статус контактов и следующий шаг.',audience='external'),
 question('internal','Внутренние дела: новые активисты, вовлечённость, кадровые потребности и организационные проблемы.',audience='internal'),
 question('media_team','Медиа: опубликовано, снято, в монтаже, лучшие материалы и потребности следующей недели.',audience='media'),
 question('chair_decisions','Какие ключевые решения и стратегические изменения произошли?',True,'chairman'),
 question('chair_meetings','Значимые встречи: организация, человек, страна, результат и следующий шаг.',False,'chairman'),
 question('chair_opportunities','Какие внешние возможности и приглашения появились?',False,'chairman'),
 question('chair_representation','Где ЭРА была представлена: событие, страна, участник и формат?',False,'chairman'),
 question('chair_risk','Какой главный риск и какие три результата нужны на следующей неделе?',True,'chairman'),
 question('external_approved','Какие факты разрешаешь использовать во внешнем отчёте? Укажи только проверенные сведения.',False,'chairman'),
]


async def questions(session):
    row=await session.scalar(select(AppSetting).where(AppSetting.key=='weekly_pulse_questions'))
    return json.loads(row.value) if row else DEFAULT_QUESTIONS


async def audiences(session,owner_id):
    row=await session.scalar(select(AppSetting).where(AppSetting.key==f'pulse_audiences:{owner_id}'))
    result=set(json.loads(row.value)) if row else set()
    offices=(await session.scalars(select(Office).join(UserOffice,UserOffice.office_id==Office.id).where(UserOffice.user_id==owner_id,UserOffice.is_active.is_(True)))).all()
    for office in offices:
        title=office.title.lower()
        if 'председатель' in title and 'заместитель' not in title: result.add('chairman')
        if 'руководитель' in title or 'заместитель' in title: result.add('head')
        if 'внешн' in title: result.add('external')
        if 'внутрен' in title: result.add('internal')
        if 'медиа' in title or 'пресс' in title: result.add('media')
    return result


async def current_form(session,owner_id,chat_id):
    now=datetime.now(timezone.utc)
    cycle=await session.scalar(select(WeeklyPulseCycle).where(WeeklyPulseCycle.leader_chat_id==chat_id,
        WeeklyPulseCycle.status=='open',WeeklyPulseCycle.opens_at<=now,WeeklyPulseCycle.deadline_at>now).order_by(WeeklyPulseCycle.opens_at.desc()).limit(1))
    if cycle is None: return None
    user=await session.get(User,owner_id)
    participant=await session.scalar(select(WeeklyPulseParticipant).where(WeeklyPulseParticipant.cycle_id==cycle.id,WeeklyPulseParticipant.user_id==owner_id))
    if participant and participant.override in {'excused','excluded'}: return None
    if participant is None:
        participant=WeeklyPulseParticipant(cycle_id=cycle.id,user_id=owner_id,telegram_user_id=user.telegram_id,status='in_progress')
        session.add(participant)
    elif participant.status!='submitted': participant.status='in_progress'
    view=await leadership_weekly_service.ensure_weekly_report(session,owner_id=owner_id,period_start=cycle.date_from)
    view.report.pulse_cycle_id=cycle.id
    data=dict(view.pulse.answers_json or {})
    if 'questions' not in data:
        groups=await audiences(session,owner_id)
        qs=[q for q in await questions(session) if q.get('is_active',True) and
            (q.get('audience','all') in groups or q.get('audience','all')=='all' and 'chairman' not in groups)]
        previous=await session.scalar(select(LeadershipReport).where(LeadershipReport.owner_id==owner_id,
            LeadershipReport.period_start<cycle.date_from,LeadershipReport.submitted_at.is_not(None)).order_by(LeadershipReport.period_start.desc()).limit(1))
        if previous and previous.next_priorities:
            qs.insert(0,question('followup','Ранее ты планировал: '+ '; '.join(previous.next_priorities)[:180]+'. Что выполнено, что в процессе и что не получилось?'))
        data={'questions':qs,'draft':{},'index':0,'audiences':sorted(groups)}
        view.pulse.answers_json=data
    return cycle,view,data


async def create_inboxes(session,report,answers):
    for key,kind in [('decision','pulse_decision'),('contacts','pulse_opportunity'),('media','pulse_media')]:
        value=answers.get(key,'').strip()
        if not value or value.lower() in {'нет','—','нет возможностей'}: continue
        item=await session.scalar(select(LeadershipAttentionItem).where(LeadershipAttentionItem.type==kind,
            LeadershipAttentionItem.scope_type=='pulse',LeadershipAttentionItem.scope_id==report.id))
        if item is None:
            item=LeadershipAttentionItem(type=kind,scope_type='pulse',scope_id=report.id,owner_id=report.owner_id,status='open',severity='medium')
            session.add(item)
        item.resolution=value[:4000]
