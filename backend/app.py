from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from investigator.cases import CASES, create_claim_pdfs
from investigator.runs import page_file, resume_run, snapshot, start_run, step_run


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_claim_pdfs()
    yield


app = FastAPI(title='Total Loss Investigator', lifespan=lifespan)
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
