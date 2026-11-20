"""Tencent CDN Type D links (decimal timestamp, sign/t, 300-second edge TTL).

The CDN must authenticate every request and authorize private COS origin pulls.
Reference: https://cloud.tencent.cn/document/product/228/41625
"""
from hashlib import md5
import re
import time
from urllib.parse import quote, urlsplit


def validate_cdn_settings(base_url: str, secret: str) -> str:
    """Return an HTTPS origin or reject partial/ambiguous configuration."""
    if not re.fullmatch(r"[A-Za-z0-9]{6,40}", secret):
        raise ValueError("Invalid CDN authentication key")
    try:
        parts = urlsplit(base_url)
        hostname = parts.hostname or ""
        valid_host = re.fullmatch(
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", hostname
        )
        if (parts.scheme != "https" or not valid_host or len(hostname) > 253
                or parts.netloc.lower() != hostname.lower()
                or parts.path not in ("", "/") or parts.query or parts.fragment
                or any(c.isspace() for c in base_url)):
            raise ValueError("Invalid CDN origin")
    except ValueError:
        raise ValueError("Invalid CDN origin") from None
    return "https://" + hostname.lower()


def signed_cdn_url(base_url: str, object_key: str, secret: str, *, timestamp=None) -> str:
    origin = validate_cdn_settings(base_url, secret)
    if (not object_key.startswith("uploads/")
            or any(part in ("", ".", "..") for part in object_key.split("/"))
            or any(c in object_key for c in "\\?#%")
            or any(ord(c) < 32 or ord(c) == 127 for c in object_key)):
        raise ValueError("Invalid CDN object key")
    issued = int(time.time()) if timestamp is None else timestamp
    if type(issued) is not int or issued <= 0:
        raise ValueError("Invalid CDN timestamp")
    path = "/" + quote(object_key, safe="/~")
    # MD5 is mandated by Tencent's Type D wire format, not used for passwords.
    signature = md5((secret + path + str(issued)).encode("utf-8")).hexdigest()
    return f"{origin}{path}?sign={signature}&t={issued}"
