# NutriFeast Insight — Upload & Ask Document RAG

Document intelligence and grounded passage retrieval workspace for PDFs, DOCX, TXT, and CSV documents with verifiable source citations and optional Google Gemini answer synthesis.

## Quick Start (Windows)
1. Double-click `start.bat` (requires Python 3.11).
2. The script automatically sets up a `.venv`, installs requirements, and launches the app at `http://127.0.0.1:8765`.
3. Drag and drop or browse for documents (PDF, DOCX, TXT, CSV up to 12 MB).
4. Select documents in the sidebar and ask questions in natural language.

## Deploy on Render
This repository includes a preconfigured `render.yaml` Blueprint for Python 3.11.

### Option A: Deploy via Blueprint (`render.yaml`)
1. In your [Render Dashboard](https://dashboard.render.com/), click **New** → **Blueprint**.
2. Connect your GitHub repository: `https://github.com/Lochan-CS/nutrifeast-document-rag`.
3. Render reads `render.yaml` automatically and configures the web service.

### Option B: Deploy as a Standard Web Service
1. In the Render Dashboard, click **New** → **Web Service**.
2. Connect `https://github.com/Lochan-CS/nutrifeast-document-rag`.
3. Configure the following settings:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. In **Environment Variables**, set:
   - `PYTHON_VERSION`: `3.11.9`
   - `GEMINI_API_KEY`: *(Optional)* Your Google Gemini API key if LLM answer synthesis is desired.
5. *(Optional)* Render filesystem is ephemeral on free tiers. If you want uploaded files and indexes to persist across service restarts, add a persistent disk mounted at `uploads`.

## Enable Gemini Generation (Optional)
The system works out-of-the-box in **Evidence-First Retrieval Mode** without an API key, returning exact passage citations with scores and page numbers.

To enable AI synthesis with Google Gemini:
```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
.\start.bat
```
On Render, set `GEMINI_API_KEY` in the service Environment Variables. You can also specify `GEMINI_MODEL` (defaults to `gemini-2.5-flash`).

## Architecture & Features
- **Document Ingestion:** Multi-format parser for PDF (`pypdf`), DOCX (`python-docx`), CSV (`csv.reader`), and TXT.
- **Smart Chunking:** Windowed passages with overlapping token boundaries preserving context.
- **Lexical Retrieval:** BM25 scoring algorithm for rapid, deterministic passage ranking across uploaded documents.
- **Grounded Refusal:** When retrieved passages lack sufficient evidence, the system refuses to speculate and requests clarification or flags insufficient data.
- **Source Citations:** Every retrieved passage is linked to its source document and exact page number.

## Contributors
- **Sahana310** — [https://github.com/Sahana310](https://github.com/Sahana310)
- **Lochan-CS** — [https://github.com/Lochan-CS](https://github.com/Lochan-CS)

> **Collaborator Access Note:**
> The repository is owned by **Lochan-CS**. To grant full write/push access to **Sahana310**, invite them as a collaborator via GitHub:
> 1. Go to repository **Settings** → **Collaborators** (`https://github.com/Lochan-CS/nutrifeast-document-rag/settings/access`).
> 2. Click **Add people** and search for `Sahana310`.
> 3. Sahana310 will receive an email/invitation notification to accept collaborator access.

## Security & Privacy
- Files and extracted passages are stored locally in the isolated `uploads/` directory.
- Protected by `.gitignore` so no uploads, indexes, API keys, or temporary files are committed to version control.
- Documents are never used to train public models.
