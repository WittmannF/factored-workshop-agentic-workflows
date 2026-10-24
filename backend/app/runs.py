import uuid
from typing import Any

from langgraph.types import Command

from .cases import ARTIFACTS
from .graph import (
    ADJUSTER_CHOICES,
    COVERAGE_SYSTEM,
    DAMAGE_SYSTEM,
    MEMO_SYSTEM,
    SUPERVISOR_SYSTEM,
    graph,
    initial_state,
)
from .llm import OPIK_PROJECT
from .ocr import EXTRACT_SYSTEM, annotated_page

TRACE_NODES = (
    ('Tesseract OCR', 'ocr'),
    ('Structured extraction', 'extract'),
    ('Confidence gate', 'confidence_gate'),
    ('Human review corrected', 'human_review'),
    ('Validated ClaimIntake', 'validate_claim'),
    ('Supervisor ->', 'supervisor'),
    ('Coverage agent', 'coverage'),
    ('Damage agent', 'damage'),
    ('Adjuster agent', 'adjuster'),
    ('Finalizer:', 'finalizer'),
)

RUNS: dict[str, dict[str, Any]] = {}


def node_of(line: str) -> str | None:
    for prefix, name in TRACE_NODES:
        if line.startswith(prefix):
            return name
    return None


def _config(thread_id: str) -> dict:
    return {'configurable': {'thread_id': thread_id}, 'recursion_limit': 35}


def _attach_opik(config: dict, case_id: str | None):
    thread_id = (config.get('configurable') or {}).get('thread_id')
    tracked = dict(config)
    tracer = None
    try:
        from opik.integrations.langchain import OpikTracer
        tracer = OpikTracer(
            project_name=OPIK_PROJECT,
            tags=[tag for tag in (case_id, 'stepper') if tag],
            metadata={'case_id': case_id},
            thread_id=str(thread_id) if thread_id else None,
            graph=graph.get_graph(),
        )
        tracked['callbacks'] = [tracer]
    except Exception as exc:
        print('Opik não rastreou o grafo:', exc)
    return tracked, tracer


def _flush_opik(tracer) -> None:
    try:
        if tracer is not None:
            tracer.flush()
        import opik
        opik.flush_tracker()
    except Exception as exc:
        print('Opik não confirmou o envio dos traces:', exc)


def _invoke(thread_id: str, payload):
    run = RUNS[thread_id]
    invoke_config, tracer = _attach_opik(_config(thread_id), run['case_id'])
    try:
        graph.invoke(payload, invoke_config)
    finally:
        _flush_opik(tracer)


def _interrupts(snapshot) -> list[Any]:
    payloads = []
    for task in snapshot.tasks:
        for item in getattr(task, 'interrupts', ()) or ():
            payloads.append(item.value)
    return payloads


def _public_field(field: dict | None) -> dict | None:
    if not field:
        return None
    return {
        'value': field.get('value'),
        'confidence': field.get('confidence'),
        'bbox': field.get('bbox'),
        'reviewed': bool(field.get('reviewed')),
        'page': field.get('page'),
    }


def _page_path(thread_id: str, values: dict):
    if not values.get('ocr') or not values['ocr'].get('images'):
        return None
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f'{thread_id}.png'
    annotated_page(values).save(path)
    return path


def _ocr_lines(values: dict) -> list[dict]:
    lines = []
    for line in (values.get('ocr') or {}).get('lines') or []:
        words = line.get('words') or []
        confidences = [float(word.get('confidence') or 0) for word in words]
        text = str(line.get('text') or '').strip()
        if not text:
            continue
        confidence = round(sum(confidences) / len(confidences), 1) if confidences else None
        lines.append({'text': text, 'confidence': confidence})
    return lines


def snapshot(thread_id: str) -> dict:
    if thread_id not in RUNS:
        raise KeyError(thread_id)
    state = graph.get_state(_config(thread_id))
    values = dict(state.values or {})
    trace = list(values.get('trace') or [])
    visit_counts: dict[str, int] = {}
    for line in trace:
        name = node_of(line)
        if name:
            visit_counts[name] = visit_counts.get(name, 0) + 1
    pending = _interrupts(state)
    if pending:
        status = 'awaiting_human'
    elif not state.next:
        status = 'finished'
    else:
        status = 'running'
    fields = {
        name: _public_field(field)
        for name, field in (values.get('fields') or {}).items()
    }
    review = None
    if pending:
        payload = pending[0] if isinstance(pending[0], dict) else {}
        kind = payload.get('kind') or ('ocr' if payload.get('fields') else 'adjuster')
        review = {
            'kind': kind,
            'message': payload.get('message'),
            'case_id': payload.get('case_id'),
            'question': payload.get('question'),
            'reason_summary': payload.get('reason_summary'),
            'packet': payload.get('packet') or {},
            'fields': {
                name: _public_field(field)
                for name, field in (payload.get('fields') or {}).items()
            },
        }
    page = _page_path(thread_id, values)
    return {
        'thread_id': thread_id,
        'case_id': RUNS[thread_id]['case_id'],
        'status': status,
        'last_node': node_of(trace[-1]) if trace else None,
        'next_nodes': list(state.next),
        'visit_counts': visit_counts,
        'trace': trace,
        'fields': fields,
        'fields_to_review': list(values.get('fields_to_review') or []),
        'routing': values.get('routing'),
        'findings': values.get('findings') or {},
        'claim': values.get('claim'),
        'final_report': values.get('final_report'),
        'human_edits': list(values.get('human_edits') or []),
        'pending_review': review,
        'page_url': f'/runs/{thread_id}/page' if page else None,
        'source_name': RUNS[thread_id].get('source_name'),
        'ocr_lines': _ocr_lines(values),
        'prompts': {
            'extract': EXTRACT_SYSTEM,
            'supervisor': SUPERVISOR_SYSTEM,
            'coverage': COVERAGE_SYSTEM,
            'damage': DAMAGE_SYSTEM,
            'finalizer': MEMO_SYSTEM,
        },
    }


def start_run(case_id: str, pdf_path: str | None = None, source_name: str | None = None) -> dict:
    thread_id = case_id if pdf_path else f'{case_id}-{uuid.uuid4().hex[:8]}'
    RUNS[thread_id] = {'case_id': case_id, 'source_name': source_name}
    _invoke(thread_id, initial_state(case_id, pdf_path))
    return snapshot(thread_id)


def step_run(thread_id: str) -> dict:
    current = snapshot(thread_id)
    if current['status'] == 'awaiting_human':
        raise RuntimeError('This run is waiting for a human response.')
    if current['status'] == 'finished':
        raise RuntimeError('This run has already finished.')
    _invoke(thread_id, None)
    return snapshot(thread_id)


def resume_run(thread_id: str, corrections: dict | None = None, answer: str | None = None, choice: str | None = None, comment: str | None = None) -> dict:
    current = snapshot(thread_id)
    if current['status'] != 'awaiting_human':
        raise RuntimeError('This run is not waiting for human review.')
    kind = (current.get('pending_review') or {}).get('kind')
    if kind == 'adjuster':
        label = ADJUSTER_CHOICES.get(choice or '')
        if not label:
            raise RuntimeError('Choose one of the adjuster responses.')
        note = (comment or '').strip()
        text = f'{label}. {note}' if note else label
        payload = {'choice': choice, 'comment': note, 'answer': text}
    else:
        payload = {'corrections': corrections or {}}
    _invoke(thread_id, Command(resume=payload))
    return snapshot(thread_id)


def page_file(thread_id: str):
    if thread_id not in RUNS:
        raise KeyError(thread_id)
    path = ARTIFACTS / f'{thread_id}.png'
    if not path.is_file():
        snapshot(thread_id)
    if not path.is_file():
        raise FileNotFoundError(thread_id)
    return path
