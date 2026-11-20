from hashlib import sha256
import hmac

from fastapi import HTTPException
import httpx

from app.core.config import Settings


async def verify_challenge(web: httpx.AsyncClient, payload: dict[str, str], settings: Settings) -> None:
    if not settings.auth_captcha_required and settings.app_env != 'production':
        return
    if not settings.geetest_id or not settings.geetest_key:
        raise HTTPException(503, '极验尚未配置')
    fields = ('lot_number', 'captcha_output', 'pass_token', 'gen_time')
    if any(not isinstance(payload.get(field), str) or not payload[field].strip() for field in fields):
        raise HTTPException(400, '请先完成行为验证')
    proof = {field: payload[field] for field in fields}
    proof['sign_token'] = hmac.new(settings.geetest_key.encode(), proof['lot_number'].encode(), sha256).hexdigest()
    try:
        response = await web.post(settings.geetest_verify_url, params={'captcha_id': settings.geetest_id}, data=proof)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError('Invalid response')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '行为验证服务暂不可用') from None
    if result.get('result') != 'success':
        raise HTTPException(401, '行为验证未通过')
