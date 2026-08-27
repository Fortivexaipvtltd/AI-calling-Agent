from __future__ import annotations

import base64
import hashlib
import hmac

from ..config import settings


def twilio_signature(url: str, params: dict[str, str], auth_token: str | None = None) -> str:
    """Compute the X-Twilio-Signature for a request.

    Twilio's scheme: take the full URL, append every POST param sorted by key
    (key then value, no delimiter), HMAC-SHA1 with the auth token, base64.
    Reference: Twilio "Validating Signatures" docs.
    """
    token = auth_token or settings.twilio_auth_token
    data = url
    for key in sorted(params):
        data += key + str(params[key])
    digest = hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_twilio(url: str, params: dict[str, str], signature: str,
                  auth_token: str | None = None) -> bool:
    """Constant-time comparison of the provided signature against the expected."""
    if not signature:
        return False
    expected = twilio_signature(url, params, auth_token)
    return hmac.compare_digest(expected, signature)
