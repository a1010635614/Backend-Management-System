from email.message import EmailMessage
import ssl

import aiosmtplib

from app.core.config import Settings


async def send_code(email: str, code: str, settings: Settings) -> None:
    message = EmailMessage()
    message['Subject'] = '纸间博客登录验证码'
    message['From'] = settings.mail_from
    message['To'] = email
    message.set_content(f'您的验证码是 {code}，{settings.email_code_ttl // 60} 分钟内有效。请勿向他人提供验证码。')
    await aiosmtplib.send(message, hostname=settings.mail_host, port=settings.mail_port,
                          username=settings.mail_username, password=settings.mail_password,
                          use_tls=settings.mail_port == 465, start_tls=settings.mail_port != 465,
                          tls_context=ssl.create_default_context(), validate_certs=True, timeout=15)
