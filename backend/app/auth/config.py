import os

APP_URL = os.environ.get('APP_URL', 'http://localhost:8080').rstrip('/')
SECRET = os.environ['AUTH_SECRET']
if len(SECRET) < 32:
    raise RuntimeError('AUTH_SECRET must contain at least 32 random characters')
SECURE = os.getenv('COOKIE_SECURE', 'true').lower() == 'true'
if not SECURE and not APP_URL.startswith(('http://localhost:', 'http://127.0.0.1:')):
    raise RuntimeError('Insecure cookies are only allowed on localhost')
if SECURE and not APP_URL.startswith('https://'):
    raise RuntimeError('Production APP_URL must use HTTPS')
