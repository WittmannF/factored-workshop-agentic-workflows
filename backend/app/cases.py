import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .config import ROOT

SAMPLES = ROOT / 'samples'
PDF_DIR = SAMPLES / 'claims'
DAMAGE_DIR = SAMPLES / 'damage'
OCR_DIR = SAMPLES / 'ocr'
FIXTURES = SAMPLES / 'insurance_fixtures.json'
ARTIFACTS = ROOT / 'artifacts'

CASES = {
    'AUTO-101': {
        'claim_id': 'AUTO-101', 'policy_id': 'POL-101', 'incident_date': '2026-10-15',
        'plate': 'ABC1D23', 'vehicle': 'Honda Civic 2020',
        'incident_type': 'Front collision', 'repair_estimate': '69000',
        'description': 'Front impact; possible hidden structural damage.',
        'policy': {'active': True, 'collision_covered': True, 'total_loss_threshold': 0.75, 'insured_value_brl': 100000},
        'damage': {
            'photo': 'AUTO-101.jpg',
            'damage_type': 'front_structural',
            'size': 'extensive',
            'repair_estimate_brl': 82000,
        },
        'valuation': {'reference_value_brl': 100000, 'basis': 'Fictional policy agreed value'},
        'history': {'prior_claims': [], 'notes': 'No prior related claims'},
    },
    'AUTO-202': {
        'claim_id': 'AUTO-202', 'policy_id': 'POL-202', 'incident_date': '2026-10-10',
        'plate': 'DEF4G56', 'vehicle': 'Toyota Corolla 2019',
        'incident_type': 'Minor side collision', 'repair_estimate': '18000',
        'description': 'Localized side door damage with complete inspection.',
        'policy': {'active': True, 'collision_covered': True, 'total_loss_threshold': 0.80, 'insured_value_brl': 80000},
        'damage': {
            'photo': 'AUTO-202.jpg',
            'damage_type': 'side_panel',
            'size': 'localized',
            'repair_estimate_brl': 18000,
        },
        'valuation': {'reference_value_brl': 80000, 'basis': 'Fictional policy agreed value'},
        'history': {'prior_claims': [], 'notes': 'No prior related claims'},
    },
    'AUTO-303': {
        'claim_id': 'AUTO-303', 'policy_id': 'POL-303', 'incident_date': '2026-10-19',
        'plate': 'GHI7J89', 'vehicle': 'Hyundai HB20 2021',
        'incident_type': 'Rear collision', 'repair_estimate': '61000',
        'description': 'Rear impact; scanned estimate and plate are blurred.',
        'policy': {'active': True, 'collision_covered': True, 'total_loss_threshold': 0.75, 'insured_value_brl': 90000},
        'damage': {
            'photo': 'AUTO-303.jpg',
            'damage_type': 'rear_panel',
            'size': 'moderate',
            'repair_estimate_brl': 61000,
        },
        'valuation': {'reference_value_brl': 90000, 'basis': 'Fictional policy agreed value'},
        'history': {'prior_claims': [{'id': 'PRIOR-11', 'status': 'closed', 'damage': 'front bumper'}], 'notes': 'Unrelated prior claim'},
    },
}

LABELS = [
    ('CLAIM ID', 'claim_id'), ('POLICY ID', 'policy_id'), ('INCIDENT DATE', 'incident_date'),
    ('PLATE', 'plate'), ('VEHICLE', 'vehicle'), ('INCIDENT TYPE', 'incident_type'),
    ('REPAIR ESTIMATE BRL', 'repair_estimate'), ('DESCRIPTION', 'description'),
]

FIELD_NAMES = [
    'claim_id', 'policy_id', 'incident_date', 'plate',
    'vehicle', 'incident_type', 'repair_estimate', 'description',
]
CRITICAL_FIELDS = ['claim_id', 'policy_id', 'incident_date', 'plate', 'repair_estimate']


def font(size, bold=False):
    candidates = [
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/Library/Fonts/Arial Bold.ttf' if bold else '/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(
        'Nenhuma fonte TrueType encontrada para gerar os PDFs. '
        'No macOS use Arial em /System/Library/Fonts/Supplemental. '
        'No Linux instale fonts-dejavu-core.'
    )


def create_claim_pdfs():
    for directory in (PDF_DIR, DAMAGE_DIR, OCR_DIR, ARTIFACTS):
        directory.mkdir(parents=True, exist_ok=True)
    for case_id, case in CASES.items():
        image = Image.new('RGB', (1654, 2339), '#ffffff')
        draw = ImageDraw.Draw(image)
        draw.rectangle((75, 70, 1579, 2270), outline='#b8c4d1', width=4)
        draw.rectangle((75, 70, 1579, 265), fill='#17324d')
        draw.text((122, 115), 'FICTIONAL INSURANCE COMPANY', font=font(45, True), fill='white')
        draw.text((122, 186), 'AUTO CLAIM INTAKE FORM  |  EDUCATIONAL SAMPLE', font=font(27), fill='#dce8f5')
        draw.text((130, 322), 'Claim Notice and Preliminary Damage Estimate', font=font(33, True), fill='#17324d')
        draw.line((120, 385, 1535, 385), fill='#b8c4d1', width=3)
        for idx, (label, key) in enumerate(LABELS):
            y = 460 + idx * 170
            value = str(case[key])
            draw.text((140, y), f'{label}:', font=font(28, True), fill='#344454')
            value_x = 565
            draw.text((value_x, y - 4), value, font=font(33), fill='#172638')
            if case_id == 'AUTO-303' and key in ('plate', 'repair_estimate'):
                bbox = (value_x - 4, y - 12, min(1530, value_x + 560), y + 63)
                crop = image.crop(bbox).filter(ImageFilter.GaussianBlur(radius=3.7))
                image.paste(crop, bbox[:2])
            draw.line((135, y + 72, 1510, y + 72), fill='#e1e6ed', width=2)
        draw.text((125, 1960), 'IMPORTANT', font=font(28, True), fill='#17324d')
        draw.text((125, 2015), 'Synthetic values. Not a real insurance policy or claim.', font=font(26), fill='#4b5d70')
        draw.text((125, 2060), 'No automatic claim approval or denial is permitted.', font=font(26), fill='#4b5d70')
        image.save(str(PDF_DIR / f'{case_id}.pdf'), 'PDF', resolution=160.0)

    support = Image.new('RGB', (1654, 1050), '#ffffff')
    draw = ImageDraw.Draw(support)
    draw.rectangle((75, 65, 1575, 990), outline='#b8c4d1', width=4)
    draw.text((130, 120), 'SUPPORTING INSPECTION DOCUMENT (SYNTHETIC)', font=font(37, True), fill='#17324d')
    draw.text((145, 320), 'CLAIM ID: AUTO-303', font=font(34), fill='#172638')
    draw.text((145, 460), 'VERIFIED PLATE: GHI7J89', font=font(34), fill='#172638')
    draw.text((145, 600), 'SIGNED REPAIR ESTIMATE BRL: 61000', font=font(34), fill='#172638')
    draw.text((145, 795), 'Educational mock document; no real customer data.', font=font(26), fill='#4b5d70')
    support.save(str(PDF_DIR / 'AUTO-303_supporting_docs.pdf'), 'PDF', resolution=160.0)
    FIXTURES.write_text(json.dumps(CASES, ensure_ascii=False, indent=2), encoding='utf-8')
    from .ocr import write_sample_ocr
    write_sample_ocr()
    return sorted(PDF_DIR.glob('*.pdf'))


if __name__ == '__main__':
    create_claim_pdfs()
