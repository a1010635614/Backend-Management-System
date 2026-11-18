"""SMTP delivery with verified TLS, including DirectMail's implicit TLS on 465."""
import smtplib
import ssl

def send_message(message, settings):
    context=ssl.create_default_context()
    if settings.mail_port==465:
        connection=smtplib.SMTP_SSL(settings.mail_host,settings.mail_port,timeout=10,context=context)
    else:
        connection=smtplib.SMTP(settings.mail_host,settings.mail_port,timeout=10)
    with connection as smtp:
        if settings.mail_port!=465:
            smtp.starttls(context=context)
        smtp.login(settings.mail_username,settings.mail_password)
        smtp.send_message(message)
