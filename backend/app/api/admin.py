from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.posts import post_view
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import current_user, permissions, require
from app.models import Asset, Post, User
from app.schemas import PostInput, UserUpdate
from app.services.storage import asset_ids, asset_view, validate_assets

router = APIRouter(prefix='/api/admin', tags=['后台管理'])
ADMIN_ROUTES = (
    {'name': 'dashboard', 'path': '/dashboard', 'component': 'Dashboard', 'title': '数据概览', 'permission': 'analytics:read'},
    {'name': 'articles', 'path': '/articles', 'component': 'Articles', 'title': '文章管理', 'permission': 'posts:read'},
    {'name': 'article-new', 'path': '/articles/new', 'component': 'Editor', 'title': '写文章', 'permission': 'posts:write', 'hidden': True},
    {'name': 'article-edit', 'path': '/articles/:id/edit', 'component': 'Editor', 'title': '编辑文章', 'permission': 'posts:write', 'hidden': True},
    {'name': 'users', 'path': '/users', 'component': 'Users', 'title': '用户与权限', 'permission': 'users:manage'},
)


@router.get('/routes')
async def routes(user: User = Depends(current_user)):
    allowed = permissions(user)
    return [route for route in ADMIN_ROUTES if route['permission'] in allowed]


def own_post(post: Post, user: User):
    if user.role != 'admin' and post.author_id != user.id:
        raise HTTPException(403, '只能管理自己创建的文章')


@router.get('/posts')
async def list_posts(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                     user: User = Depends(require('posts:read')), db: AsyncSession = Depends(get_db)):
    filters = [] if user.role == 'admin' else [Post.author_id == user.id]
    total = await db.scalar(select(func.count()).select_from(Post).where(*filters))
    rows = (await db.scalars(select(Post).where(*filters).order_by(Post.updated_at.desc(), Post.id.desc())
                             .offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [post_view(post) for post in rows], 'total': total, 'page': page, 'pageSize': page_size}


@router.get('/posts/{post_id}')
async def get_post(post_id: int, user: User = Depends(require('posts:read')), db: AsyncSession = Depends(get_db)):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(404, '文章不存在')
    own_post(post, user)
    ids = asset_ids(post.content)
    assets = (await db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.state == 'ready'))).all() if ids else []
    return {**post_view(post, True), 'attachments': [asset_view(asset) for asset in assets]}


@router.post('/posts', status_code=201)
async def create_post(body: PostInput, user: User = Depends(require('posts:write')), db: AsyncSession = Depends(get_db)):
    await validate_assets(body.content, user, db)
    post = Post(**body.model_dump(), author_id=user.id, read_minutes=max(1, len(body.content) // 500))
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post_view(post, True)


@router.put('/posts/{post_id}')
async def edit_post(post_id: int, body: PostInput, user: User = Depends(require('posts:write')),
                    db: AsyncSession = Depends(get_db)):
    post = await db.scalar(select(Post).where(Post.id == post_id).with_for_update())
    if not post:
        raise HTTPException(404, '文章不存在')
    own_post(post, user)
    await validate_assets(body.content, user, db)
    for key, value in body.model_dump().items():
        setattr(post, key, value)
    post.read_minutes = max(1, len(post.content) // 500)
    await db.commit()
    await db.refresh(post)
    return post_view(post, True)


@router.delete('/posts/{post_id}', status_code=204)
async def delete_post(post_id: int, user: User = Depends(require('posts:delete')), db: AsyncSession = Depends(get_db)):
    post = await db.scalar(select(Post).where(Post.id == post_id).with_for_update())
    if not post:
        raise HTTPException(404, '文章不存在')
    own_post(post, user)
    await db.delete(post)
    await db.commit()
    return Response(status_code=204)


@router.get('/users')
async def users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                user: User = Depends(require('users:manage')), db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(User))
    rows = (await db.scalars(select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [{'id': row.id, 'email': row.email, 'role': row.role, 'is_active': row.is_active,
                        'createdAt': row.created_at.isoformat()} for row in rows], 'total': count}


@router.patch('/users/{user_id}')
async def edit_user(user_id: int, body: UserUpdate, actor: User = Depends(require('users:manage')),
                    db: AsyncSession = Depends(get_db)):
    target = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not target:
        raise HTTPException(404, '用户不存在')
    if target.id == actor.id and (body.role != 'admin' or not body.is_active):
        raise HTTPException(400, '不能撤销自己的管理员权限')
    if target.email.lower() in get_settings().administrators and (body.role != 'admin' or not body.is_active):
        raise HTTPException(400, '不能禁用配置指定的管理员')
    target.role, target.is_active = body.role, body.is_active
    await db.commit()
    return {'id': target.id, 'email': target.email, 'role': target.role, 'is_active': target.is_active}
