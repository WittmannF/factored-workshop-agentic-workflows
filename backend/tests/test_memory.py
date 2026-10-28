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


def test_snapshot_writes_the_page_once(monkeypatch, tmp_path):
    from app import runs

    saves = []

    class Page:
        def save(self, path):
            saves.append(path)
            Path(path).write_bytes(b'png')

    monkeypatch.setattr(runs, 'ARTIFACTS', tmp_path)
    monkeypatch.setattr(runs, 'annotated_page', lambda _values: Page())
    monkeypatch.setattr(runs.graph, 'get_state', lambda _config: SimpleNamespace(
        values={
            'trace': ['Tesseract OCR: AUTO-101'],
            'ocr': {'images': [{'path': 'page.png', 'page': 1}], 'lines': []},
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
    assert len(saves) == 1
