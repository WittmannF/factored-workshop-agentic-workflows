# Total Loss Investigator

A local claims desk for a fictional insurer. The investigation advances one step at a time. The memo is a preliminary recommendation and does not authorize payment.

## Run

Tesseract must be on the PATH (`brew install tesseract` on macOS). Put `OPENROUTER_API_KEY` in `.env` at the project root, next to this file.

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5174`. Set `RUN_LIVE_LLM=false` in front of uvicorn to use the simulated supervisor, with no model call and no API key.

With a local Opik server at `http://localhost:5173`, each run appears in the `total-loss-investigator` project.

## Flow

The desk reads the claim document, extracts the fields, and passes them through a confidence gate. A low-confidence read pauses for OCR review. Coverage and damage are investigated next. The supervisor may consult an adjuster once, after both are complete, and must do so when the repair-to-reference ratio meets the policy threshold. The investigation memo is the only ending.

The adjuster's answer is recorded on the memo. It does not change the estimate, the reference value, the ratio, or the calculated recommendation.

## Cases

- AUTO-101 reaches the adjuster consult at an 82% ratio and a total-loss review.
- AUTO-202 finishes as a repair review, with no consult.
- AUTO-303 pauses at OCR review. After the plate and estimate are corrected, it finishes as a repair review.
