"""Symmetric encryption for provider credentials at rest.

**What this actually buys, stated plainly:** it protects a database dump. The
nightly `pg_dump` leaves the machine; the application does not. A leaked backup
holding a Fitbit client secret and a refresh token in the clear is a real
exposure, and this closes it.

It does **not** protect against a compromised container. The app has to be able
to decrypt in order to call Fitbit, so anything running as the app can too.
Encrypting at rest is worth doing here because backups travel and processes do
not - not because it makes the secret unreachable.

Fernet, not a hand-rolled construction: AES-128-CBC with an HMAC, an IV per
message and a timestamp, all of which are easy to get wrong separately.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

#: Domain separation. A key derived for this purpose must not collide with one
#: derived from the same secret for anything else later.
INFO = b"selfhealthos.health.provider-credentials.v1"


class CannotDecrypt(RuntimeError):
    """The stored value will not decrypt under the current key.

    Almost always means the signing key changed. The fix is to reconnect the
    provider, not to recover the value - which is why this is a distinct
    exception the UI can turn into "reconnect Fitbit".
    """


def _key() -> bytes:
    """A Fernet key derived from the configured secret.

    Derived rather than used directly because `DJANGO_SECRET_KEY` is an
    arbitrary string and Fernet needs 32 url-safe base64 bytes.
    """
    material = (settings.CREDENTIAL_ENCRYPTION_KEY or settings.SECRET_KEY).encode()
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=INFO).derive(material)
    return base64.urlsafe_b64encode(derived)


def encrypt(value: str) -> str:
    """Encrypt a secret for storage. Empty in, empty out - a connection with no
    tokens yet stores an empty string rather than the ciphertext of nothing."""
    if not value:
        return ""
    return Fernet(_key()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if not value:
        return ""
    try:
        return Fernet(_key()).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise CannotDecrypt(
            "Stored credentials cannot be decrypted with the current key. "
            "If the signing key was rotated, reconnect the provider."
        ) from exc
