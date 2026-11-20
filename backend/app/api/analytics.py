from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import rate_limit
from app.core.database import get_db
from app.core.security import require
from app.models import Event, Post, User
from app.schemas import TrackInput

router = APIRouter(prefix='/api/analytics', tags=['访问统计'])


@router.post('/events', status_code=202)
async def collect(body: TrackInput, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else 'unknown'
    await rate_limit(request.app.state.redis, 'analytics:' + ip, 120, 60)
    db.add(Event(event_name=body.event, path=body.path, visitor_id=body.visitorId, referrer=body.referrer))
    await db.commit()
    return {'status': 'accepted'}


@router.get('/summary')
async def summary(user: User = Depends(require('analytics:read')), db: AsyncSession = Depends(get_db)):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    pv, uv = (await db.execute(select(func.count(Event.id), func.count(func.distinct(Event.visitor_id)))
                               .where(Event.created_at >= today, Event.created_at < today + timedelta(days=1),
                                      Event.event_name == 'pageview'))).one()
    totals = (await db.execute(select(Post.status, func.count()).group_by(Post.status))).all()
    days = (await db.execute(select(func.date(Event.created_at).label('day'), func.count(Event.id),
                                     func.count(func.distinct(Event.visitor_id)))
                             .where(Event.created_at >= today - timedelta(days=6), Event.event_name == 'pageview')
                             .group_by('day').order_by('day'))).all()
    return {'pv': pv, 'uv': uv, 'posts': dict(totals), 'timezone': 'UTC',
            'daily': [{'day': str(day), 'pv': count, 'uv': unique} for day, count, unique in days]}
