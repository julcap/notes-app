from fastapi import APIRouter

# Shared by routes.py (local email/password) and oauth.py (social login).
router = APIRouter(prefix='/api/auth')
