# NutriFeast Insight — Upload & Ask Document RAG

## Windows quick start
1. Extract the ZIP (do not run from inside the ZIP).
2. Double-click `start.bat` (requires Python 3.11 and internet for first-time package installation).
3. Open http://127.0.0.1:8765.
4. Upload PDF, DOCX, TXT, or CSV; select document; ask a question.

## Deploy on Render
This repository includes a `render.yaml` Blueprint for Python 3.11. Create a Render Web Service from the repository, then optionally set `GEMINI_API_KEY` in the service environment to enable Gemini generation. Uploaded files and the document index are stored under `uploads/`; Render's default filesystem is ephemeral, so configure a persistent disk mounted at the project's `uploads` directory if uploads must survive service restarts or redeploys.

## Enable Gemini generation (optional, but required for LLM-based RAG)
Open PowerShell in the extracted folder and run:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
.\start.bat
```

With no Gemini key, the app retrieves and cites relevant passages, but does not claim to generate an LLM answer. Uses Google Gemini API over the internet when configured. Change model via `GEMINI_MODEL` if necessary.

## Architecture
Upload -> text extraction (pypdf / python-docx / UTF-8 CSV/TXT) -> overlapping chunks -> BM25 ranked passage retrieval -> Gemini answer restricted to passages -> citations.

**Note:** This compact ready-to-run version uses BM25 lexical retrieval, not FAISS semantic vector retrieval. It is a genuine document-grounded retrieval + optional generation pipeline, but does not claim to implement embeddings. It intentionally does not use the pre-existing USDA dataset.

## Security and limitations
- Files and extracted text are stored locally under `uploads/` (not suitable for shared multiuser hosting).
- 12 MB upload limit. Scanned PDFs without selectable text are not supported.
- No user accounts; do not deploy publicly without authentication and per-user storage isolation.
- Retrieved snippets are evidence, not proof of factual correctness. Test citations manually.
- Python 3.11 is recommended; port 8765 avoids conflict with your existing project on port 8000.
