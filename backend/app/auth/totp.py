import base64
import hashlib
import secrets

import pyotp
import qrcode
import qrcode.image.svg
from cryptography.fernet import Fernet, InvalidToken

from .config import APP_URL, SECRET

# Derived from AUTH_SECRET with domain separation, kept out of the database so a DB
# leak alone cannot decrypt stored TOTP secrets (unlike a password, these must be
# readable again to check codes, so hashing them like a password isn't an option).
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b'totp-encryption:' + SECRET.encode()).digest()))


def generate_secret():
    return pyotp.random_base32()


def encrypt_secret(secret):
    return _fernet.encrypt(secret.encode()).decode()


def decrypt_secret(token):
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def otpauth_uri(secret, email):
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=APP_URL.split('//')[-1])


def qr_svg(uri):
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()


def verify_code(secret, code):
    return bool(code) and pyotp.TOTP(secret).verify(code.strip(), valid_window=1)


def generate_backup_codes(count=10):
    return ['-'.join([secrets.token_hex(2), secrets.token_hex(2)]) for _ in range(count)]
