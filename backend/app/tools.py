import json
import urllib.error
import urllib.request
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .cases import CASES
from .llm import openrouter_vision_structured

RAW_BASE = (
    'https://raw.githubusercontent.com/WittmannF/'
    'factored-workshop-agentic-workflows/main/mock_data/damage'
)
DAMAGE_TYPES = ('front_structural', 'side_panel', 'rear_panel')
DAMAGE_SIZES = ('localized', 'moderate', 'extensive')

VISION_SYSTEM = (
    'You inspect a photo of vehicle damage for an insurance investigation. '
    'Choose damage_type from front_structural, side_panel, rear_panel. '
    'Choose size from localized, moderate, extensive. '
    'notes is one short sentence about what is visible. '
    'Do not estimate a repair cost. These photos are educational samples.'
)


class DamageObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    damage_type: Literal['front_structural', 'side_panel', 'rear_panel']
    size: Literal['localized', 'moderate', 'extensive']
    notes: str


def image_url(case_id: str) -> str:
    photo = CASES[case_id]['damage']['photo']
    return f'{RAW_BASE}/{photo}'


def case_for_claim(claim_id: str) -> str | None:
    return _case_for_claim(claim_id)


def case_for_document(claim_id: str, policy_id: str) -> str | None:
    found = _case_for_claim(str(claim_id or ''))
    if found and CASES[found]['policy_id'] == policy_id:
        return found
    return None


def _case_for_claim(claim_id: str) -> str | None:
    for case_id, case in CASES.items():
        if case_id == claim_id or case.get('claim_id') == claim_id:
            return case_id
    return None


def _case_for_policy(policy_id: str) -> str | None:
    for case_id, case in CASES.items():
        if case.get('policy_id') == policy_id:
            return case_id
    return None


def _case_from_urls(image_urls) -> str | None:
    for url in image_urls or []:
        for case_id in CASES:
            if case_id in str(url):
                return case_id
    return None


def _priced(case_id: str) -> dict:
    damage = CASES[case_id]['damage']
    return {
        'damage_type': damage['damage_type'],
        'size': damage['size'],
        'repair_estimate_brl': damage['repair_estimate_brl'],
        'basis': 'Case price table',
    }


def _fixture_observation(case_id: str | None) -> dict:
    if case_id not in CASES:
        return {
            'damage_type': None,
            'size': None,
            'notes': '',
            'source': 'fixture',
        }
    priced = _priced(case_id)
    return {
        'damage_type': priced['damage_type'],
        'size': priced['size'],
        'notes': '',
        'source': 'fixture',
    }


def _public_image(url: str) -> bool:
    request = urllib.request.Request(
        url,
        method='GET',
        headers={'User-Agent': 'total-loss-investigator/0.1'},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            content_type = response.headers.get('Content-Type', '')
            return response.status == 200 and content_type.startswith('image/')
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def retrieve_evidence(claim_id: str) -> dict:
    case_id = _case_for_claim(str(claim_id))
    if case_id is None:
        return {'image_urls': [], 'warning': 'No evidence for this claim.'}
    return {'image_urls': [image_url(case_id)]}


def extract_damage_features(image_urls: list[str] | str, case_id: str | None = None) -> dict:
    urls = [image_urls] if isinstance(image_urls, str) else list(image_urls or [])
    resolved = case_id or _case_from_urls(urls)
    if not urls or not all(_public_image(url) for url in urls):
        return _fixture_observation(resolved)
    try:
        seen = openrouter_vision_structured(
            DamageObservation,
            VISION_SYSTEM,
            'Describe the vehicle damage in this photo.',
            urls,
        )
    except Exception:
        return _fixture_observation(resolved)
    return {
        'damage_type': seen.damage_type,
        'size': seen.size,
        'notes': seen.notes.strip(),
        'source': 'live',
    }


def calculate_costs(damage_features: dict | str) -> dict:
    if isinstance(damage_features, str):
        try:
            damage_features = json.loads(damage_features)
        except json.JSONDecodeError:
            damage_features = {}
    if not isinstance(damage_features, dict):
        damage_features = {}
    case_id = _case_for_claim(str(damage_features.get('claim_id') or ''))
    if case_id is None:
        return {'repair_estimate_brl': None, 'basis': 'Case price table', 'warning': 'Unknown claim.'}
    return {**_priced(case_id), 'claim_id': case_id}


def retrieve_insurance_coverage(policy_id: str) -> dict:
    case_id = _case_for_policy(str(policy_id))
    if case_id is None:
        return {
            'active': False,
            'collision_covered': False,
            'total_loss_threshold': None,
            'insured_value_brl': None,
            'prior_claims': [],
            'history_notes': '',
            'warning': 'Policy ID discrepancy',
        }
    case = CASES[case_id]
    return {
        **case['policy'],
        'prior_claims': case['history']['prior_claims'],
        'history_notes': case['history']['notes'],
    }


def reference_value(vehicle_data: dict | str) -> dict:
    if isinstance(vehicle_data, str):
        try:
            vehicle_data = json.loads(vehicle_data)
        except json.JSONDecodeError:
            vehicle_data = {}
    if not isinstance(vehicle_data, dict):
        vehicle_data = {}
    vehicle = str(vehicle_data.get('vehicle') or '')
    plate = str(vehicle_data.get('plate') or '')
    for case in CASES.values():
        if case['vehicle'] == vehicle and case['plate'] == plate:
            price = case['valuation']['reference_value_brl']
            return {
                'estimated_price': price,
                'reference_value_brl': price,
                'basis': case['valuation']['basis'],
            }
    return {
        'estimated_price': None,
        'reference_value_brl': None,
        'basis': None,
        'warning': 'No reference value for this vehicle.',
    }


def _object_schema(properties: dict, required: list[str]) -> dict:
    return {
        'type': 'object',
        'properties': properties,
        'required': required,
        'additionalProperties': False,
    }


def _tool_schema(name: str, description: str, parameters: dict) -> dict:
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': parameters,
        },
    }


_STRING = {'type': 'string'}

DAMAGE_SCHEMAS = [
    _tool_schema(
        'retrieve_evidence',
        'Return the damage photo URLs for a claim.',
        _object_schema({'claim_id': _STRING}, ['claim_id']),
    ),
    _tool_schema(
        'extract_damage_features',
        'Read damage type and size from the photo URLs.',
        _object_schema({
            'image_urls': {'type': 'array', 'items': _STRING},
        }, ['image_urls']),
    ),
    _tool_schema(
        'calculate_costs',
        'Price the repair from the case table. The vision label does not change the price.',
        _object_schema({
            'damage_features': _object_schema({
                'claim_id': _STRING,
                'damage_type': {'type': 'string', 'enum': list(DAMAGE_TYPES)},
                'size': {'type': 'string', 'enum': list(DAMAGE_SIZES)},
            }, ['claim_id', 'damage_type', 'size']),
        }, ['damage_features']),
    ),
]

COVERAGE_SCHEMAS = [
    _tool_schema(
        'retrieve_insurance_coverage',
        'Return the policy coverage for a policy id.',
        _object_schema({'policy_id': _STRING}, ['policy_id']),
    ),
    _tool_schema(
        'reference_value',
        'Return the reference price for a vehicle and plate.',
        _object_schema({
            'vehicle_data': _object_schema({
                'vehicle': _STRING,
                'plate': _STRING,
            }, ['vehicle', 'plate']),
        }, ['vehicle_data']),
    ),
]

DAMAGE_HANDLERS = {
    'retrieve_evidence': retrieve_evidence,
    'extract_damage_features': extract_damage_features,
    'calculate_costs': calculate_costs,
}

COVERAGE_HANDLERS = {
    'retrieve_insurance_coverage': retrieve_insurance_coverage,
    'reference_value': reference_value,
}
