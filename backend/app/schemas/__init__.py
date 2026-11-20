import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, EmailStr, Field, field_validator


class EmailRequest(BaseModel):
    email: EmailStr
    geetest: dict[str, str] = Field(default_factory=dict)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class VerifyRequest(EmailRequest):
    code: str = Field(pattern=r'^\d{6}$')


class PostInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    summary: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=200_000)
    category: str = Field(default='生活随笔', min_length=1, max_length=60)
    status: Literal['draft', 'published'] = 'draft'

    @field_validator('title', 'summary', 'category')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('字段不能为空')
        return value.strip()


class UploadInput(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    contentType: Literal['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
    size: int = Field(gt=0, le=10 * 1024 * 1024)


class TrackInput(BaseModel):
    event: Literal['pageview']
    path: str = Field(min_length=1, max_length=500)
    visitorId: str = Field(pattern=r'^[a-zA-Z0-9-]{16,100}$')
    referrer: str | None = Field(default=None, max_length=1000)

    @field_validator('path')
    @classmethod
    def path_only(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or not value.startswith('/') or value.startswith('//'):
            raise ValueError('仅允许站内路径')
        return parsed.path

    @field_validator('referrer')
    @classmethod
    def origin_only(cls, value):
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname:
            return None
        return f'{parsed.scheme}://{parsed.hostname}'


class UserUpdate(BaseModel):
    role: Literal['admin', 'editor', 'viewer']
    is_active: bool
