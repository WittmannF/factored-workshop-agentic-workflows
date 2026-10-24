import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .config import OPIK_PROJECT, get_settings

OCR_THRESHOLD = 86.0
MAX_DELEGATIONS = 5
OPENROUTER_PRICE_PER_M_INPUT = 0.065
OPENROUTER_PRICE_PER_M_OUTPUT = 0.26

LLM_USAGE: list[dict] = []
_OPENROUTER_CLIENT = None


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
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            f'Set OPENROUTER_API_KEY in {settings.env_path} or in the environment.'
        )
    from openai import OpenAI
    client = OpenAI(base_url='https://openrouter.ai/api/v1', api_key=settings.openrouter_api_key, timeout=60.0)
    try:
        from opik.integrations.openai import track_openai
        client = track_openai(client, project_name=OPIK_PROJECT, provider='openrouter')
    except Exception as exc:
        print('Opik não rastreou o cliente OpenRouter:', exc)
    _OPENROUTER_CLIENT = client
    return client


def _record_usage(completion) -> None:
    usage = completion.usage
    if not usage:
        return
    in_tokens = usage.prompt_tokens or 0
    out_tokens = usage.completion_tokens or 0
    LLM_USAGE.append({
        'model': get_settings().openrouter_model,
        'input_tokens': in_tokens,
        'output_tokens': out_tokens,
        'estimated_usd': round(
            in_tokens * OPENROUTER_PRICE_PER_M_INPUT / 1e6
            + out_tokens * OPENROUTER_PRICE_PER_M_OUTPUT / 1e6, 6),
    })


def _prepared_system(schema: type[BaseModel], system: str) -> str:
    if 'json' not in system.lower():
        system = system.rstrip() + ' Return one JSON object and nothing else.'
    return system.rstrip() + ' Use exactly these JSON keys: ' + ', '.join(schema.model_fields) + '.'


def _complete_structured(schema: type[BaseModel], messages: list[dict]):
    settings = get_settings()
    client = openrouter_client()
    last_error: Exception | None = None
    for _attempt in range(2):
        completion = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=messages,
            temperature=0,
            response_format={'type': 'json_schema', 'json_schema': {
                'name': schema.__name__, 'strict': True, 'schema': schema.model_json_schema()}},
            extra_body={
                'provider': {'require_parameters': True},
                'reasoning': {'enabled': False},
            },
        )
        _record_usage(completion)
        content = completion.choices[0].message.content or ''
        try:
            data = _coerce_string_fields(schema, _json_object(content))
            return schema.model_validate(data)
        except Exception as exc:
            last_error = exc
            messages = [
                *messages,
                {'role': 'assistant', 'content': content},
                {'role': 'user', 'content': (
                    'That response did not match the schema: ' + str(exc)[:1200]
                    + ' Return only the corrected JSON object.'
                )},
            ]
    raise RuntimeError(f'OpenRouter structured output failed after retry: {last_error}') from last_error


def openrouter_structured(schema: type[BaseModel], system: str, payload: str):
    messages = [
        {'role': 'system', 'content': _prepared_system(schema, system)},
        {'role': 'user', 'content': payload},
    ]
    return _complete_structured(schema, messages)


def openrouter_vision_structured(schema: type[BaseModel], system: str, text: str, image_urls: list[str]):
    content = [{'type': 'text', 'text': text}]
    content.extend(
        {'type': 'image_url', 'image_url': {'url': url}}
        for url in image_urls
    )
    messages = [
        {'role': 'system', 'content': _prepared_system(schema, system)},
        {'role': 'user', 'content': content},
    ]
    return _complete_structured(schema, messages)


def _tool_arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def run_tool_loop(system: str, user: str, schemas: list[dict], handlers: dict, max_rounds: int = 6) -> list[dict]:
    settings = get_settings()
    client = openrouter_client()
    messages: list[dict] = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]
    calls: list[dict] = []
    for _round in range(max_rounds):
        completion = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=messages,
            tools=schemas,
            temperature=0,
            extra_body={'reasoning': {'enabled': False}},
        )
        _record_usage(completion)
        message = completion.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            break
        messages.append({
            'role': 'assistant',
            'content': message.content or '',
            'tool_calls': [
                {
                    'id': call.id,
                    'type': 'function',
                    'function': {
                        'name': call.function.name,
                        'arguments': call.function.arguments or '{}',
                    },
                }
                for call in tool_calls
            ],
        })
        for call in tool_calls:
            name = call.function.name
            arguments = _tool_arguments(call.function.arguments)
            handler = handlers.get(name)
            if handler is None:
                result = {'error': f'Unknown tool: {name}'}
            else:
                try:
                    result = handler(**arguments)
                except TypeError:
                    result = {'error': f'{name} received unexpected arguments.'}
                except Exception as exc:
                    result = {'error': str(exc)[:500]}
            calls.append({'name': name, 'arguments': arguments, 'result': result})
            messages.append({
                'role': 'tool',
                'tool_call_id': call.id,
                'content': json.dumps(result, ensure_ascii=False, default=str),
            })
    return calls
