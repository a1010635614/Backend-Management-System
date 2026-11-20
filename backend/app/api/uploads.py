from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require
from app.models import User
from app.schemas import UploadInput
from app.services.storage import complete_upload, download_url, presign_upload, preview_url

router = APIRouter(prefix='/api', tags=['附件'])


@router.post('/uploads/presign')
async def presign(body: UploadInput, user: User = Depends(require('uploads:write')), db: AsyncSession = Depends(get_db)):
    return await presign_upload(body, user, db)


@router.post('/uploads/{asset_id}/complete')
async def complete(asset_id: str, user: User = Depends(require('uploads:write')), db: AsyncSession = Depends(get_db)):
    return await complete_upload(asset_id, user, db)


@router.get('/uploads/{asset_id}/preview')
async def preview(asset_id: str, response: Response, user: User = Depends(require('uploads:write')),
                  db: AsyncSession = Depends(get_db)):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return {'url': await preview_url(asset_id, user, db), 'expiresIn': 300}


@router.get('/media/{asset_id}', response_class=RedirectResponse)
async def media(asset_id: str, db: AsyncSession = Depends(get_db)):
    return RedirectResponse(await download_url(asset_id, db), status_code=307,
                            headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer'})
