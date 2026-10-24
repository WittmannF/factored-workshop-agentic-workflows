# Agentic workflows

Companion repo for the Factored technical workshop on agent-based workflows. The worked example is a fictional auto-claims desk: a LangGraph investigation you can advance one step at a time, with a React Flow view of the same graph.

The desk reads a claim, routes work to specialist steps, and can pause for a person. The memo at the end is a preliminary recommendation. It does not authorize payment.

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

Open `http://127.0.0.1:5174`. The desk requires `OPENROUTER_API_KEY`.

## Railway

The Dockerfile builds the page and the API into one service. Railway reads `railway.toml`, injects `PORT`, and must have `OPENROUTER_API_KEY` set on the service. Do not commit `.env`.

The public domain is the desk. The same process serves the page and the `/api` routes. Runs stay in the process memory and disappear on redeploy. Opik stays on a local server and is skipped when that server is absent.

With a local Opik server at `http://localhost:5173`, each run appears in the `total-loss-investigator` project.

## Flow

The desk reads the claim document, extracts the fields, and passes them through a confidence gate. A low-confidence read pauses for OCR review. Coverage and damage each run once, as tool-calling agents. Coverage calls the policy and the reference value. Damage calls the photo URL, a vision read of that photo, and a price table. The supervisor may consult an adjuster once, after both are complete, and must do so when the repair-to-reference ratio meets the policy threshold. The investigation memo is the only ending.

The adjuster's answer is recorded on the memo. It does not change the estimate, the reference value, the ratio, or the calculated recommendation.

## Cases

- AUTO-101 reaches the adjuster consult at an 82% ratio and a total-loss review. The intake form shows 69,000. The damage tools price the repair at 82,000.
- AUTO-202 finishes as a repair review at 22.5%, with no consult.
- AUTO-303 pauses at OCR review. After the plate and estimate are corrected, it finishes as a repair review at 67.8%, with no consult.
