import asyncio
from functools import lru_cache
import re
import secrets
from uuid import uuid4

from fastapi import HTTPException
from qcloud_cos import CosConfig, CosS3Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cdn import signed_cdn_url
from app.core.config import get_settings
from app.models import Asset, Post, User
from app.schemas import UploadInput

ASSET_PATTERN = re.compile(r'\[\[asset:([a-f0-9-]{36})\]\]')


@lru_cache
def cos_client() -> CosS3Client:
    settings = get_settings()
    if not all((settings.cos_bucket, settings.cos_secret_id, settings.cos_secret_key)):
        raise HTTPException(503, 'COS 尚未配置')
    return CosS3Client(CosConfig(Region=settings.cos_region, SecretId=settings.cos_secret_id,
                                 SecretKey=settings.cos_secret_key, Scheme='https'))


def asset_ids(content: str) -> set[str]:
    return set(ASSET_PATTERN.findall(content))


def asset_view(asset: Asset) -> dict:
    return {'id': asset.id, 'filename': asset.filename, 'contentType': asset.content_type,
            'size': asset.size, 'url': '/api/media/' + asset.id}


async def validate_assets(content: str, user: User, db: AsyncSession) -> None:
    ids = asset_ids(content)
    if not ids:
        return
    if len(ids) > 50:
        raise HTTPException(400, '每篇文章最多关联 50 个附件')
    query = select(Asset.id).where(Asset.id.in_(ids), Asset.state == 'ready')
    if user.role != 'admin':
        query = query.where(Asset.owner_id == user.id)
    found = set((await db.scalars(query)).all())
    if found != ids:
        raise HTTPException(400, '文章引用了不可用或无权使用的附件')


async def presign_upload(body: UploadInput, user: User, db: AsyncSession) -> dict:
    settings = get_settings()
    extensions = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'application/pdf': 'pdf'}
    filename = body.filename.replace('\\', '/').split('/')[-1]
    if not filename.strip() or any(ord(c) < 32 for c in filename):
        raise HTTPException(400, '文件名无效')
    asset = Asset(id=str(uuid4()), key=f'uploads/{user.id}/{secrets.token_hex(16)}.{extensions[body.contentType]}',
                  filename=filename, content_type=body.contentType, size=body.size, owner_id=user.id)
    try:
        url = await asyncio.to_thread(cos_client().get_presigned_url, Bucket=settings.cos_bucket,
                                      Key=asset.key, Method='PUT', Expired=300,
                                      Headers={'Content-Type': body.contentType, 'Content-Length': str(body.size)})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '上传地址生成失败') from None
    db.add(asset)
    await db.commit()
    return {'id': asset.id, 'uploadUrl': url, 'key': asset.key, 'expiresIn': 300}


async def complete_upload(asset_id: str, user: User, db: AsyncSession) -> dict:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.owner_id != user.id:
        raise HTTPException(404, '附件不存在')
    if asset.state == 'ready':
        return asset_view(asset)
    if asset.state != 'pending':
        raise HTTPException(400, '该上传已被拒绝，请重新上传')
    settings = get_settings()
    try:
        metadata = await asyncio.to_thread(cos_client().head_object, Bucket=settings.cos_bucket, Key=asset.key)
        values = {key.lower(): value for key, value in metadata.items()}
        size = int(values.get('content-length', -1))
        content_type = values.get('content-type', '').split(';')[0].strip().lower()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '无法确认 COS 对象，请检查上传是否完成') from None
    if size != asset.size or content_type != asset.content_type:
        asset.state = 'rejected'
        await db.commit()
        raise HTTPException(400, '文件实际大小或类型与声明不符')
    asset.state = 'ready'
    await db.commit()
    return asset_view(asset)


async def download_url(asset_id: str, db: AsyncSession) -> str:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.state != 'ready':
        raise HTTPException(404, '附件不存在')
    published = await db.scalar(select(Post.id).where(Post.status == 'published',
                               Post.content.contains('[[asset:' + asset.id + ']]')).limit(1))
    if not published:
        raise HTTPException(404, '附件尚未公开')
    settings = get_settings()
    if settings.cdn_base_url or settings.cdn_auth_key:
        try:
            return signed_cdn_url(settings.cdn_base_url, asset.key, settings.cdn_auth_key)
        except ValueError:
            raise HTTPException(503, 'CDN 下载配置无效') from None
    try:
        return await asyncio.to_thread(cos_client().get_presigned_url, Bucket=settings.cos_bucket,
                                        Key=asset.key, Method='GET', Expired=300)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '附件地址生成失败') from None


async def preview_url(asset_id: str, user: User, db: AsyncSession) -> str:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.state != 'ready' or (user.role != 'admin' and asset.owner_id != user.id):
        raise HTTPException(404, '附件不存在')
    settings = get_settings()
    if settings.cdn_base_url and settings.cdn_auth_key:
        return signed_cdn_url(settings.cdn_base_url, asset.key, settings.cdn_auth_key)
    try:
        return await asyncio.to_thread(cos_client().get_presigned_url, Bucket=settings.cos_bucket,
                                        Key=asset.key, Method='GET', Expired=300)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, '附件预览生成失败') from None
