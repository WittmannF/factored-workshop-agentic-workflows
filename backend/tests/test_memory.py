import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pymupdf

EMPTY_OCR = {
    'text': [],
    'conf': [],
    'left': [],
    'top': [],
    'width': [],
    'height': [],
    'block_num': [],
    'par_num': [],
    'line_num': [],
}


def _tiny_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((36, 72), 'CLAIM ID: AUTO-101')
    doc.save(path)
    doc.close()


def test_one_tesseract_at_a_time(monkeypatch, tmp_path):
    from app import ocr

    monkeypatch.setattr(ocr, 'ARTIFACTS', tmp_path)
    pdf = tmp_path / 'claim.pdf'
    _tiny_pdf(pdf)

    arrived = []
    release = threading.Event()
    guard = threading.Lock()

    def blocked(_image, **_kwargs):
        with guard:
            arrived.append(1)
        assert release.wait(timeout=3)
        return EMPTY_OCR

    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', blocked)
    threads = [threading.Thread(target=ocr.ocr_pdf, args=(pdf,)) for _ in range(3)]
    for thread in threads:
        thread.start()
    time.sleep(0.5)
    try:
        assert len(arrived) == 1
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=3)
            assert not thread.is_alive()


def test_snapshot_copies_the_page_once(monkeypatch, tmp_path):
    from app import runs

    source = tmp_path / 'AUTO-101.png'
    source.write_bytes(b'png-bytes')
    artifacts = tmp_path / 'artifacts'
    copies = []
    real_copy = runs.shutil.copy

    def spy(src, dst, *args, **kwargs):
        copies.append(Path(dst))
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(runs.shutil, 'copy', spy)
    monkeypatch.setattr(runs, 'ARTIFACTS', artifacts)
    monkeypatch.setattr(runs.graph, 'get_state', lambda _config: SimpleNamespace(
        values={
            'trace': ['Tesseract OCR: AUTO-101'],
            'ocr': {'images': [{'path': str(source), 'page': 1}], 'lines': []},
            'fields': {},
        },
        tasks=[],
        next=('extract',),
    ))
    runs.RUNS['thread-1'] = {'case_id': 'AUTO-101'}
    try:
        runs.snapshot('thread-1')
        runs.snapshot('thread-1')
    finally:
        runs.RUNS.pop('thread-1', None)
    assert copies == [artifacts / 'thread-1.png']
    assert (artifacts / 'thread-1.png').read_bytes() == b'png-bytes'


def test_sample_case_reads_cached_ocr(monkeypatch, tmp_path):
    from app import cases, ocr

    claims = tmp_path / 'claims'
    cache = tmp_path / 'ocr'
    claims.mkdir()
    cache.mkdir()
    sample = claims / 'AUTO-101.pdf'
    _tiny_pdf(sample)
    (cache / 'AUTO-101.json').write_text(
        '{"images":[{"page":1,"path":"AUTO-101.png","width":10,"height":10}],"words":[],"lines":[]}',
        encoding='utf-8',
    )
    (cache / 'AUTO-101.png').write_bytes(b'png')
    monkeypatch.setattr(cases, 'PDF_DIR', claims)
    monkeypatch.setattr(cases, 'OCR_DIR', cache)
    calls = []
    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', lambda *_args, **_kwargs: calls.append(1))
    result = ocr.ocr_node({'case_id': 'AUTO-101', 'pdf_path': str(sample)})
    assert calls == []
    assert result['ocr']['images'][0]['path'] == str((cache / 'AUTO-101.png').resolve())
    assert result['trace'] == ['Tesseract OCR: AUTO-101']


def test_other_pdf_still_runs_tesseract(monkeypatch, tmp_path):
    from app import ocr

    monkeypatch.setattr(ocr, 'ARTIFACTS', tmp_path)
    pdf = tmp_path / 'upload.pdf'
    _tiny_pdf(pdf)
    calls = []

    def blocked(_image, **_kwargs):
        calls.append(1)
        return EMPTY_OCR

    monkeypatch.setattr(ocr.pytesseract, 'image_to_data', blocked)
    ocr.ocr_node({'case_id': 'upload-1', 'pdf_path': str(pdf)})
    assert calls == [1]
