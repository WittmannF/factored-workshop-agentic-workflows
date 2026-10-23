import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .cases import SANDBOX

OCR_THRESHOLD = 86.0
OPENROUTER_MODEL = 'qwen/qwen3.5-flash-02-23'
MAX_DELEGATIONS = 5
OPIK_PROJECT = 'total-loss-investigator'
OPENROUTER_PRICE_PER_M_INPUT = 0.065
OPENROUTER_PRICE_PER_M_OUTPUT = 0.26

os.environ.setdefault('OPIK_URL_OVERRIDE', 'http://localhost:5173/api')
os.environ.setdefault('OPIK_WORKSPACE', 'default')
os.environ['OPIK_PROJECT_NAME'] = OPIK_PROJECT

LLM_USAGE: list[dict] = []
_OPENROUTER_CLIENT = None


def load_project_env() -> None:
    roots = [Path.cwd().resolve(), SANDBOX.resolve()]
    seen = set()
    for root in roots:
        for directory in [root, *root.parents]:
            env_path = directory / '.env'
            if env_path in seen or not env_path.is_file():
                if directory == directory.parent:
                    break
                continue
            seen.add(env_path)
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path, override=False)
            except ImportError:
                for raw in env_path.read_text(encoding='utf-8').splitlines():
                    line = raw.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    name, value = line.split('=', 1)
                    os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
            if directory == directory.parent:
                break


def get_openrouter_key() -> str | None:
    load_project_env()
    key = os.environ.get('OPENROUTER_API_KEY')
    if key:
        key = key.strip().strip('"').strip("'")
    return key or None


def live_mode() -> bool:
    flag = os.environ.get('RUN_LIVE_LLM', 'true').strip().lower()
    return flag in {'1', 'true', 'yes'}


USE_LIVE_LLM = live_mode()
OPENROUTER_KEY = get_openrouter_key() if USE_LIVE_LLM else None
if USE_LIVE_LLM and not OPENROUTER_KEY:
    raise ValueError('Defina OPENROUTER_API_KEY no .env da raiz do projeto ou no ambiente.')


class RawClaimFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_id: str | None
    policy_id: str | None
    incident_date: str | None
    plate: str | None
    vehicle: str | None
    incident_type: str | None
    repair_estimate: str | None
    description: str | None


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    next_agent: Literal['coverage', 'damage', 'adjuster', 'FINISH']
    question: str
    reason_summary: str


class FinalReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    claim_id: str
    recommendation: Literal['TOTAL_LOSS_REVIEW', 'REPAIR_REVIEW', 'REQUEST_MORE_EVIDENCE', 'HUMAN_REVIEW']
    coverage_status: str
    repair_estimate_brl: float | None
    reference_value_brl: float | None
    loss_ratio: float | None
    evidence_ids: list[str]
    unresolved_issues: list[str]
    justification: str
    human_review_required: bool


def _json_object(text: str) -> dict:
    text = (text or '').strip()
    if not text:
        raise RuntimeError('OpenRouter did not provide structured content.')
    if re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', text):
        raise RuntimeError('OpenRouter returned a corrupted numeric payload instead of JSON.')
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise RuntimeError('Structured output was not a JSON object.')
    return data


def _coerce_string_fields(schema: type[BaseModel], data: dict) -> dict:
    coerced = dict(data)
    for name, field in schema.model_fields.items():
        value = coerced.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        annotation = field.annotation
        args = set(getattr(annotation, '__args__', ()))
        allows_str = annotation is str or (str in args and float not in args and int not in args)
        if not allows_str:
            continue
        if isinstance(value, float) and value.is_integer():
            coerced[name] = str(int(value))
        else:
            coerced[name] = str(value)
    return coerced


def openrouter_client():
    global _OPENROUTER_CLIENT
    if _OPENROUTER_CLIENT is not None:
        return _OPENROUTER_CLIENT
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=OPENROUTER_KEY, timeout=60.0)
    try:
        from opik.integrations.openai import track_openai
        client = track_openai(client, project_name=OPIK_PROJECT, provider='openrouter')
    except Exception as exc:
        print('Opik não rastreou o cliente OpenRouter:', exc)
    _OPENROUTER_CLIENT = client
    return client


def openrouter_structured(schema: type[BaseModel], system: str, payload: str):
    if not USE_LIVE_LLM:
        raise RuntimeError('OpenRouter is disabled; deterministic mock mode is active.')
    client = openrouter_client()
    if 'json' not in system.lower():
        system = system.rstrip() + ' Return one JSON object and nothing else.'
    system = system.rstrip() + ' Use exactly these JSON keys: ' + ', '.join(schema.model_fields) + '.'
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': payload},
    ]
    last_error: Exception | None = None
    for _attempt in range(2):
        completion = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            temperature=0,
            response_format={'type': 'json_schema', 'json_schema': {
                'name': schema.__name__, 'strict': True, 'schema': schema.model_json_schema()}},
            extra_body={
                'provider': {'require_parameters': True},
                'reasoning': {'enabled': False},
            },
        )
        usage = completion.usage
        if usage:
            in_tokens = usage.prompt_tokens or 0
            out_tokens = usage.completion_tokens or 0
            LLM_USAGE.append({
                'model': OPENROUTER_MODEL,
                'input_tokens': in_tokens,
                'output_tokens': out_tokens,
                'estimated_usd': round(
                    in_tokens * OPENROUTER_PRICE_PER_M_INPUT / 1e6
                    + out_tokens * OPENROUTER_PRICE_PER_M_OUTPUT / 1e6, 6),
            })
        content = completion.choices[0].message.content or ''
        try:
            data = _coerce_string_fields(schema, _json_object(content))
            return schema.model_validate(data)
        except Exception as exc:
            last_error = exc
            messages = [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': payload},
                {'role': 'assistant', 'content': content},
                {'role': 'user', 'content': (
                    'That response did not match the schema: ' + str(exc)[:1200]
                    + ' Return only the corrected JSON object.'
                )},
            ]
    raise RuntimeError(f'OpenRouter structured output failed after retry: {last_error}') from last_error
