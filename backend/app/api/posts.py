from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import rate_limit
from app.core.database import get_db
from app.models import Asset, Post
from app.services.storage import asset_ids, asset_view

router = APIRouter(prefix='/api', tags=['博客'])


def post_view(post: Post, detail=False) -> dict:
    value = {'id': post.id, 'title': post.title, 'summary': post.summary, 'category': post.category,
             'status': post.status, 'readMinutes': post.read_minutes, 'views': post.views,
             'likes': post.likes, 'createdAt': post.created_at.isoformat(), 'updatedAt': post.updated_at.isoformat()}
    if detail:
        value['content'] = post.content
    return value


@router.get('/posts')
async def posts(page: int = Query(1, ge=1), page_size: int = Query(9, ge=1, le=50),
                q: str = Query('', max_length=100), category: str = Query('', max_length=60),
                db: AsyncSession = Depends(get_db)):
    filters = [Post.status == 'published']
    if q.strip():
        pattern = '%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        filters.append(Post.title.ilike(pattern, escape='\\') | Post.summary.ilike(pattern, escape='\\'))
    if category:
        filters.append(Post.category == category)
    total = await db.scalar(select(func.count()).select_from(Post).where(*filters))
    rows = (await db.scalars(select(Post).where(*filters).order_by(Post.created_at.desc(), Post.id.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [post_view(post) for post in rows], 'total': total, 'page': page, 'pageSize': page_size}


@router.get('/categories')
async def categories(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Post.category, func.count(Post.id)).where(Post.status == 'published')
                             .group_by(Post.category).order_by(Post.category))).all()
    return [{'name': name, 'count': count} for name, count in rows]


@router.get('/posts/{post_id}')
async def detail(post_id: int, db: AsyncSession = Depends(get_db)):
    post = await db.scalar(select(Post).where(Post.id == post_id, Post.status == 'published'))
    if not post:
        raise HTTPException(404, '文章不存在')
    ids = asset_ids(post.content)
    assets = (await db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.state == 'ready'))).all() if ids else []
    return {**post_view(post, True), 'attachments': [asset_view(asset) for asset in assets]}


@router.post('/posts/{post_id}/view', status_code=202)
async def record_view(post_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else 'unknown'
    await rate_limit(request.app.state.redis, f'view:{ip}:{post_id}', 1, 60)
    result = await db.execute(update(Post).where(Post.id == post_id, Post.status == 'published').values(views=Post.views + 1))
    if not result.rowcount:
        raise HTTPException(404, '文章不存在')
    await db.commit()
    return {'status': 'accepted'}
