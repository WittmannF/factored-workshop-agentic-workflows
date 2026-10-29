import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .cases import ARTIFACTS, CASES
from .config import ROOT, require_live_settings
from .runs import page_file, resume_run, snapshot, start_run, step_run

DESK = ROOT / 'frontend' / 'dist'


@asynccontextmanager
async def lifespan(_app: FastAPI):
    require_live_settings()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    yield


class StripApiPrefix:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope.get('path') or ''
            if path == '/api' or path.startswith('/api/'):
                scope = dict(scope)
                scope['path'] = path[4:] or '/'
                scope['raw_path'] = scope['path'].encode('utf-8')
        await self.app(scope, receive, send)


app = FastAPI(title='Total Loss Investigator', lifespan=lifespan)
app.add_middleware(StripApiPrefix)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://127.0.0.1:5174', 'http://localhost:5174'],
    allow_methods=['*'],
    allow_headers=['*'],
)


class StartBody(BaseModel):
    case_id: str


class ResumeBody(BaseModel):
    corrections: dict[str, str] = Field(default_factory=dict)
    answer: str | None = None
    choice: str | None = None
    comment: str | None = None


def _missing(thread_id: str):
    raise HTTPException(status_code=404, detail=f'Unknown run {thread_id}')


@app.get('/cases')
def list_cases():
    return {
        'cases': [
            {'id': case_id, 'vehicle': case['vehicle'], 'incident_type': case['incident_type']}
            for case_id, case in CASES.items()
        ]
    }


@app.post('/runs')
def create_run(body: StartBody):
    if body.case_id not in CASES:
        raise HTTPException(status_code=404, detail=f'Unknown case {body.case_id}')
    try:
        return start_run(body.case_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/runs/upload')
async def upload_run(file: UploadFile = File(...)):
    name = (file.filename or '').rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    payload = await file.read()
    if not name.lower().endswith('.pdf') or not payload.startswith(b'%PDF'):
        raise HTTPException(status_code=400, detail='Upload a PDF claim form.')
    uploads = ARTIFACTS / 'uploads'
    uploads.mkdir(parents=True, exist_ok=True)
    case_id = f'upload-{uuid.uuid4().hex[:8]}'
    path = uploads / f'{case_id}.pdf'
    path.write_bytes(payload)
    try:
        return start_run(case_id, str(path), name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/runs/{thread_id}')
def get_run(thread_id: str):
    try:
        return snapshot(thread_id)
    except KeyError:
        _missing(thread_id)


@app.post('/runs/{thread_id}/step')
def step(thread_id: str):
    try:
        return step_run(thread_id)
    except KeyError:
        _missing(thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/runs/{thread_id}/resume')
def resume(thread_id: str, body: ResumeBody):
    try:
        return resume_run(thread_id, body.corrections, body.answer, body.choice, body.comment)
    except KeyError:
        _missing(thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/runs/{thread_id}/page')
def page(thread_id: str):
    try:
        return FileResponse(page_file(thread_id), media_type='image/png')
    except KeyError:
        _missing(thread_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='Annotated page is not ready') from None


if DESK.is_dir():
    app.mount('/', StaticFiles(directory=DESK, html=True), name='desk')
