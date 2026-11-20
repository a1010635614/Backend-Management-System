from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.mail import send_code


@pytest.mark.parametrize('port,use_tls,start_tls', [(465, True, False), (587, False, True)])
async def test_async_smtp_preserves_tls_and_hostname_verification(monkeypatch, port, use_tls, start_tls):
    sender = AsyncMock()
    monkeypatch.setattr('app.services.mail.aiosmtplib.send', sender)
    settings = Settings(_env_file=None, mail_host='smtp.example.com', mail_port=port,
                        mail_username='test@example.com', mail_password='fixture-password', mail_from='test@example.com')
    await send_code('recipient@example.com', '123456', settings)
    kwargs = sender.await_args.kwargs
    assert kwargs['use_tls'] is use_tls and kwargs['start_tls'] is start_tls
    assert kwargs['validate_certs'] is True and kwargs['tls_context'].check_hostname
    assert sender.await_count == 1
