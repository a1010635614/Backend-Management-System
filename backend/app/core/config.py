from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', hide_input_in_errors=True)

    app_env: Literal['development', 'test', 'production'] = 'development'
    database_url: str = Field(default='postgresql+asyncpg://blog:blog@localhost:5432/blog', repr=False)
    redis_url: str = Field(default='redis://localhost:6379/0', repr=False)
    jwt_secret: str = Field(default='development-only-change-this-secret-key', repr=False)
    jwt_exp_minutes: int = Field(default=60, ge=5, le=1440)
    jwt_issuer: str = 'blog-fullstack'
    admin_emails: str = ''
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174'
    allowed_hosts: str = 'localhost,127.0.0.1,testserver'
    docs_enabled: bool = True
    auth_captcha_required: bool = True
    email_code_ttl: int = Field(default=300, ge=60, le=600)
    email_code_attempts: int = Field(default=5, ge=1, le=10)
    mail_host: str = ''
    mail_port: int = 465
    mail_username: str = ''
    mail_password: str = Field(default='', repr=False)
    mail_from: str = 'noreply@example.com'
    geetest_id: str = ''
    geetest_key: str = Field(default='', repr=False)
    geetest_verify_url: str = 'https://gcaptcha4.geetest.com/validate'
    cos_secret_id: str = Field(default='', repr=False)
    cos_secret_key: str = Field(default='', repr=False)
    cos_region: str = 'ap-shanghai'
    cos_bucket: str = ''
    cdn_base_url: str = ''
    cdn_auth_key: str = Field(default='', repr=False)
    baidu_hm_id: str = ''
    analytics_retention_days: int = Field(default=30, ge=1, le=365)

    @field_validator('database_url')
    @classmethod
    def async_database(cls, value: str) -> str:
        if not value.startswith('postgresql+asyncpg://'):
            raise ValueError('DATABASE_URL must use postgresql+asyncpg')
        return value

    @model_validator(mode='after')
    def production_security(self):
        if self.app_env == 'production':
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith('development-'):
                raise ValueError('Production requires a strong JWT_SECRET of at least 32 characters')
            if not self.admin_emails.strip():
                raise ValueError('Production requires ADMIN_EMAILS')
            if not self.auth_captcha_required:
                raise ValueError('Production requires Geetest verification')
            if '*' in self.allowed_hosts.split(','):
                raise ValueError('Production requires explicit ALLOWED_HOSTS')
        if self.cdn_base_url or self.cdn_auth_key:
            from app.cdn import validate_cdn_settings
            validate_cdn_settings(self.cdn_base_url, self.cdn_auth_key)
        return self

    @property
    def administrators(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(',') if email.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
