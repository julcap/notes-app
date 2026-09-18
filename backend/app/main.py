from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth import SECRET, SECURE
from .auth import router as auth_router
from .database import Base, db, engine
from .error_tracking import initialize_error_tracking
from .metrics import install_metrics
from .notes.routes import action_items_router
from .notes.routes import router as notes_router
from .observability import ObservedFastAPI
from .rate_limits import ApiRateLimitMiddleware
from .storage import STORAGE, LocalStorage, storage
from .notes.sharing import notes_sharing_router, sharing_router


@asynccontextmanager
async def lifespan(app):
    if isinstance(storage, LocalStorage):
        storage.root.mkdir(parents=True, exist_ok=True)
    yield

initialize_error_tracking()
app = ObservedFastAPI(title='Minutes API', lifespan=lifespan)
install_metrics(app)

app.add_middleware(ApiRateLimitMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SECRET, https_only=SECURE, same_site='lax', max_age=600)
app.include_router(auth_router)
app.include_router(notes_router)
app.include_router(action_items_router)
app.include_router(notes_sharing_router)
app.include_router(sharing_router)

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
