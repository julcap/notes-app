from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import SECRET, SECURE
from .auth import router as auth_router
from .database import Base, db, engine
from .notes.routes import STORAGE
from .notes.routes import action_items_router
from .notes.routes import router as notes_router


@asynccontextmanager
async def lifespan(app):
    STORAGE.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title='Minutes API', lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SECRET, https_only=SECURE, same_site='lax', max_age=600)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(action_items_router)

@app.middleware('http')
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/api/health')
def health(session: Session = Depends(db)):
    session.execute(text('SELECT 1'))
    return {'status': 'ok'}
