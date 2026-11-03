import copy
import difflib
import json
import re
import shutil
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract
from PIL import Image
from pytesseract import Output

from .cases import ARTIFACTS, CRITICAL_FIELDS, FIELD_NAMES, LABELS
from .llm import OCR_THRESHOLD, RawClaimFields, openrouter_structured

_OCR_LOCK = threading.Lock()


def ocr_pdf(pdf_path):
    with _OCR_LOCK:
        return _recognize_pdf(pdf_path)


def _recognize_pdf(pdf_path):
    images, words, lines = [], [], []
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(str(pdf_path)) as doc:
        for page_idx, page in enumerate(doc):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            image_path = ARTIFACTS / f'ocr_{pdf_path.stem}_page_{page_idx + 1}.png'
            image.save(image_path)
            images.append({
                'page': page_idx + 1, 'path': str(image_path),
                'width': pix.width, 'height': pix.height,
            })
            data = pytesseract.image_to_data(image, lang='eng', config='--psm 6', output_type=Output.DICT)
            buckets = {}
            for i, token in enumerate(data['text']):
                token = token.strip()
                if not token:
                    continue
                confidence = float(data['conf'][i])
                entry = {
                    'id': f'p{page_idx + 1}-w{i}', 'text': token, 'confidence': confidence,
                    'bbox': [int(data[k][i]) for k in ('left', 'top', 'width', 'height')],
                    'page': page_idx + 1,
                }
                words.append(entry)
                key = (int(data['block_num'][i]), int(data['par_num'][i]), int(data['line_num'][i]))
                buckets.setdefault(key, []).append(entry)
            for entries in buckets.values():
                lines.append({
                    'page': page_idx + 1,
                    'text': ' '.join(word['text'] for word in entries),
                    'words': entries,
                })
    return {'images': images, 'words': words, 'lines': lines}


def write_sample_ocr():
    from .cases import CASES, OCR_DIR, PDF_DIR
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    for case_id in CASES:
        recognized = ocr_pdf(PDF_DIR / f'{case_id}.pdf')
        image = recognized['images'][0]
        shutil.copy(image['path'], OCR_DIR / f'{case_id}.png')
        stored = {
            'images': [{
                'page': image['page'],
                'path': f'{case_id}.png',
                'width': image['width'],
                'height': image['height'],
            }],
            'words': recognized['words'],
            'lines': recognized['lines'],
        }
        (OCR_DIR / f'{case_id}.json').write_text(json.dumps(stored), encoding='utf-8')


def load_sample_ocr(case_id: str, pdf_path: str) -> dict | None:
    from .cases import CASES, OCR_DIR, PDF_DIR
    if case_id not in CASES:
        return None
    sample = (PDF_DIR / f'{case_id}.pdf').resolve()
    if Path(pdf_path).resolve() != sample:
        return None
    cache = OCR_DIR / f'{case_id}.json'
    if not cache.is_file():
        return None
    payload = json.loads(cache.read_text(encoding='utf-8'))
    payload['images'] = [
        {**image, 'path': str((OCR_DIR / image['path']).resolve())}
        for image in payload['images']
    ]
    return copy.deepcopy(payload)


def _label_normalize(text):
    text = re.sub(r'[^A-Z0-9]', '', text.upper())
    return text.replace('1', 'I').replace('0', 'O')


def parse_label_lines(ocr):
    if not ocr.get('words'):
        raise RuntimeError('Tesseract returned no words. Inspect the rendered PDF and OCR configuration.')

    fields = {}
    for line in ocr['lines']:
        tokens = line['words']
        if not tokens:
            continue
        best = None
        for label, key in LABELS:
            n = len(label.split())
            for count in range(max(1, n - 1), min(len(tokens), n + 1) + 1):
                prefix = ' '.join(word['text'] for word in tokens[:count])
                score = difflib.SequenceMatcher(None, _label_normalize(prefix), _label_normalize(label)).ratio()
                if not best or score > best[0]:
                    best = (score, key, count)
        if not best or best[0] < 0.90:
            continue

        score, key, label_count = best
        if key in fields and fields[key]['label_match_score'] >= score:
            continue
        value_tokens = tokens[label_count:]
        while value_tokens and value_tokens[0]['text'].strip() in {':', '-', '=', '|'}:
            value_tokens = value_tokens[1:]
        value = ' '.join(word['text'] for word in value_tokens).strip() or None
        bounds = [word['bbox'] for word in value_tokens]
        if not bounds:
            label_boxes = [word['bbox'] for word in tokens[:label_count]]
            last_right = max(box[0] + box[2] for box in label_boxes)
            y1 = min(box[1] for box in label_boxes)
            y2 = max(box[1] + box[3] for box in label_boxes)
            image_info = next((im for im in ocr.get('images', []) if im['page'] == line['page']), {})
            max_width = image_info.get('width', last_right + 300)
            bounds = [[last_right + 8, y1, max(32, min(350, max_width - last_right - 15)), max(24, y2 - y1)]]
        x1 = min(box[0] for box in bounds)
        y1 = min(box[1] for box in bounds)
        x2 = max(box[0] + box[2] for box in bounds)
        y2 = max(box[1] + box[3] for box in bounds)
        confidences = [word['confidence'] for word in value_tokens if word['confidence'] >= 0]
        fields[key] = {
            'value': value,
            'confidence': min(confidences) if confidences else 0.0,
            'bbox': [x1, y1, x2 - x1, y2 - y1],
            'page': line['page'],
            'source_word_ids': [word['id'] for word in value_tokens],
            'reviewed': False,
            'label_match_score': score,
        }

    for name in FIELD_NAMES:
        fields.setdefault(name, {
            'value': None, 'confidence': 0.0, 'bbox': None, 'page': 1,
            'source_word_ids': [], 'reviewed': False, 'label_match_score': None,
        })
    matched = sum(fields[name]['value'] is not None for name in CRITICAL_FIELDS)
    if matched == 0:
        raw = '\n'.join(line['text'] for line in ocr['lines'][:12])
        raise RuntimeError(
            'OCR found text, but could not associate any critical field. '
            'Inspect the lines below; check scan orientation and language.\n' + raw
        )
    return fields


EXTRACT_SYSTEM = (
    'You extract insurance claim fields from OCR text. Never infer obscured, missing, '
    'or illegible characters. Use null for unreadable fields. Return only schema fields. '
    'These are synthetic insurance documents.'
)


def extract_claim(state):
    fields = parse_label_lines(state['ocr'])
    lines = '\n'.join(line['text'] for line in state['ocr']['lines'])
    response = openrouter_structured(
        RawClaimFields,
        EXTRACT_SYSTEM,
        lines,
    )
    values = response.model_dump()
    for name in FIELD_NAMES:
        value = values[name]
        observed = fields[name]['value']
        if value is None:
            continue
        if observed is not None:
            similarity = difflib.SequenceMatcher(None, str(value).casefold(), str(observed).casefold()).ratio()
            if similarity < 0.70:
                fields[name]['confidence'] = 0.0
        else:
            fields[name]['confidence'] = 0.0
        fields[name]['value'] = value
    return {'fields': fields, 'trace': ['Structured extraction (OpenRouter)']}


def ocr_node(state):
    cached = load_sample_ocr(state['case_id'], state['pdf_path'])
    recognized = cached if cached is not None else ocr_pdf(Path(state['pdf_path']))
    return {'ocr': recognized, 'trace': ['Tesseract OCR: ' + state['case_id']]}


def confidence_gate(state):
    failed = []
    for name in CRITICAL_FIELDS:
        field = state['fields'][name]
        if not field['value'] or field['confidence'] < OCR_THRESHOLD:
            failed.append(name)
    if 'incident_date' not in failed:
        try:
            date.fromisoformat(str(state['fields']['incident_date']['value']))
        except ValueError:
            failed.append('incident_date')
    plate = str(state['fields']['plate']['value']).upper()
    if 'plate' not in failed and not re.fullmatch(r'[A-Z]{3}\d[A-Z0-9]\d{2}', plate):
        failed.append('plate')
    return {
        'fields_to_review': failed,
        'trace': [f'Confidence gate: {len(failed)} field(s) flagged at {OCR_THRESHOLD:.0f}%'],
    }


def route_gate(state):
    return 'human_review' if state['fields_to_review'] else 'validate_claim'


def parse_brl(value: Any) -> float | None:
    if value is None:
        return None
    text = re.sub(r'[^\d,.]', '', str(value))
    if not text:
        return None
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None
