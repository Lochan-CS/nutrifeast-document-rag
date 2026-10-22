import os, re, csv, io, json, math, uuid, hashlib, logging, tempfile, shutil
from pathlib import Path
from collections import Counter
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from pypdf import PdfReader
from docx import Document
import requests

BASE = Path(__file__).resolve().parent
logger = logging.getLogger("nutrifeast")

def init_storage() -> Path:
    env_dir = os.getenv("UPLOADS_DIR")
    if env_dir:
        store = Path(env_dir)
    elif os.getenv("RENDER") or (os.name != "nt" and Path("/tmp").is_dir()):
        store = Path("/tmp/nutrifeast_uploads")
    else:
        store = BASE / "uploads"
    
    store.mkdir(parents=True, exist_ok=True)
    
    # Preserve and migrate legacy documents from BASE / 'uploads' so no user files are lost
    local_uploads = BASE / "uploads"
    if store.resolve() != local_uploads.resolve() and local_uploads.exists():
        try:
            for item in local_uploads.iterdir():
                dest = store / item.name
                if not dest.exists() and item.is_file():
                    shutil.copy2(item, dest)
        except Exception as e:
            logger.warning("Could not migrate legacy files from %s to %s: %s", local_uploads, store, e)
            
    return store

STORE = init_storage()
INDEX = STORE / "index.json"
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_storage()
    yield

app = FastAPI(title="NutriFeast Document Intelligence", lifespan=lifespan)

MAX_BYTES = 12 * 1024 * 1024  # 12 MB
MAX_EXTRACT_CHARS = 1_000_000  # Cap at 1M characters to protect Render memory
EXT = {".pdf", ".docx", ".txt", ".csv"}
STOP = set("the a an and or of for to in is are was were on at by from with as it this that which what how much many does do can should i you we they their about give tell me please according based document uploaded".split())

def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

def words(s):
    return [w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 1 and w not in STOP]

def load():
    if not INDEX.exists():
        return {"documents": []}
    try:
        content = INDEX.read_text("utf-8").strip()
        if not content:
            return {"documents": []}
        data = json.loads(content)
        if isinstance(data, dict) and "documents" in data:
            return data
        return {"documents": []}
    except Exception as e:
        logger.exception("Unable to read document index %s, resetting gracefully", INDEX)
        return {"documents": []}

def save(db):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STORE, prefix="index.", suffix=".tmp", delete=False) as f:
            temp_path = Path(f.name)
            json.dump(db, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, INDEX)
    except Exception as e:
        logger.warning("Atomic index write failed on %s: %s; falling back to direct write", INDEX, e)
        if temp_path:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            INDEX.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e2:
            logger.exception("Unable to save document index %s", INDEX)
            raise HTTPException(500, f"Unable to save document library index ({e2}). Check folder permissions.") from e2

def extract(name, data):
    suffix = Path(name).suffix.lower()
    pages = []
    
    if suffix == ".pdf":
        try:
            d = PdfReader(io.BytesIO(data), strict=False)
        except Exception as e:
            logger.exception("Unable to parse PDF %s", name)
            raise HTTPException(400, f'Unable to read PDF "{name}". The file may be corrupt or not a valid PDF.') from e

        if getattr(d, "is_encrypted", False):
            unlocked = False
            for empty_pw in ("", b""):
                try:
                    status = d.decrypt(empty_pw)
                    if status != 0:
                        unlocked = True
                        break
                except Exception:
                    pass
            if not unlocked:
                raise HTTPException(400, f'PDF "{name}" is password-protected. Please upload an unencrypted PDF.')

        try:
            num_pages = len(d.pages)
        except Exception as e:
            logger.exception("Unable to inspect pages of %s", name)
            raise HTTPException(400, f'Unable to inspect pages of PDF "{name}". The document structure may be damaged.') from e

        for i in range(num_pages):
            t = ""
            try:
                p = d.pages[i]
                t = (p.extract_text() or "").strip()
            except Exception as e:
                logger.warning("Page %s text extraction failed in %s: %s", i + 1, name, e)
            pages.append({"page": i + 1, "text": t})
            
    elif suffix == ".docx":
        try:
            d = Document(io.BytesIO(data))
            t = "\n".join([p.text for p in d.paragraphs] + [" | ".join(c.text for c in r.cells) for table in d.tables for r in table.rows])
            pages = [{"page": None, "text": t}]
        except Exception as e:
            logger.exception("Unable to read DOCX %s", name)
            raise HTTPException(400, f'Unable to read DOCX "{name}". Ensure the document is a valid Microsoft Word file.') from e
            
    elif suffix == ".csv":
        try:
            s = decode_text(data)
            rows = list(csv.reader(io.StringIO(s)))
            pages = [{"page": None, "text": "\n".join(" | ".join(r) for r in rows)}]
        except Exception as e:
            logger.exception("Unable to read CSV %s", name)
            raise HTTPException(400, f'Unable to parse CSV "{name}". Ensure it is valid text.') from e
            
    else:  # .txt
        try:
            s = decode_text(data)
            pages = [{"page": None, "text": s}]
        except Exception as e:
            logger.exception("Unable to read TXT %s", name)
            raise HTTPException(400, f'Unable to parse text file "{name}".') from e

    return pages

def chunks(pages):
    out = []
    total_chars = 0
    for p in pages:
        s = re.sub(r"\s+", " ", p["text"]).strip()
        start = 0
        while start < len(s):
            end = min(start + 1050, len(s))
            if end < len(s):
                k = s.rfind(" ", start + 650, end)
                if k > start:
                    end = k
            text = s[start:end].strip()
            if text:
                out.append({"page": p["page"], "text": text})
                total_chars += len(text)
                if total_chars > MAX_EXTRACT_CHARS:
                    logger.warning("Document excerpt truncated at %s characters to prevent memory exhaustion", MAX_EXTRACT_CHARS)
                    return out
            if end == len(s):
                break
            start = max(start + 1, end - 160)
    return out

# Storage initialized via lifespan context manager

@app.get("/")
def home():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "documents": len(load()["documents"]), "gemini_configured": bool(os.getenv("GEMINI_API_KEY")), "storage_dir": str(STORE)}

@app.get("/api/documents")
def documents():
    return [{k: v for k, v in d.items() if k != "chunks"} | {"chunks_count": len(d["chunks"])} for d in load()["documents"]]

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(400, "Invalid file: filename is missing.")
    if Path(name).suffix.lower() not in EXT:
        raise HTTPException(400, f'Unsupported file type for "{name}". Allowed formats: PDF, DOCX, TXT, CSV.')
    if file.size is not None and file.size > MAX_BYTES:
        raise HTTPException(413, f'File "{name}" exceeds the 12 MB upload limit. Reduce the file size and try again.')
        
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f'File "{name}" exceeds the 12 MB upload limit. Reduce the file size and try again.')
    if not data:
        raise HTTPException(400, f'File "{name}" is empty (0 bytes).')

    ps = await run_in_threadpool(extract, name, data)
    cs = await run_in_threadpool(chunks, ps)
    
    if not cs:
        if Path(name).suffix.lower() == ".pdf":
            raise HTTPException(400, f'No searchable text was found in "{name}". This PDF may be scanned or image-only; please upload a PDF with selectable text or OCR.')
        raise HTTPException(400, f'No searchable text was found in "{name}".')

    db = load()
    did = uuid.uuid4().hex[:12]
    doc = {"id": did, "name": name, "size": len(data), "pages": len(ps), "chunks": cs}
    path = STORE / (did + Path(name).suffix.lower())
    
    try:
        path.write_bytes(data)
    except OSError as e:
        logger.exception("Unable to save uploaded file %s", path)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(500, f'Unable to save uploaded file "{name}" ({e}). Check permissions of storage directory {STORE}.') from e

    db["documents"].append(doc)
    try:
        save(db)
    except HTTPException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    return {"id": did, "name": name, "chunks_count": len(cs), "pages": len(ps)}

@app.delete("/api/documents/{did}")
def delete(did: str):
    db = load()
    before = len(db["documents"])
    db["documents"] = [d for d in db["documents"] if d["id"] != did]
    if len(db["documents"]) == before:
        raise HTTPException(404, "Document not found")
    save(db)
    for f in STORE.glob(did + ".*"):
        if f.name != "index.json":
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
    return {"ok": True}

class Query(BaseModel):
    question: str
    document_ids: list[str]

@app.post("/api/ask")
def ask(q: Query):
    if not q.question.strip():
        raise HTTPException(400, "Enter a question")
    db = load()
    docs = [d for d in db["documents"] if d["id"] in q.document_ids]
    if not docs:
        raise HTTPException(400, "Select at least one uploaded document")
    corpus = [{"doc": d["name"], "doc_id": d["id"], **c} for d in docs for c in d["chunks"]]
    query = words(q.question)
    if not query:
        return {"answer": "Please ask a more specific question.", "citations": [], "mode": "refusal"}
    doc_terms = [Counter(words(c["text"])) for c in corpus]
    df = Counter(w for cnt in doc_terms for w in cnt)
    avg = sum(sum(c.values()) for c in doc_terms) / max(1, len(doc_terms))
    scored = []
    for i, counts in enumerate(doc_terms):
        length = sum(counts.values())
        score = 0
        for w in set(query):
            tf = counts[w]
            if tf:
                score += math.log(1 + (len(corpus) - df[w] + .5) / (df[w] + .5)) * (tf * 2.2) / (tf + 1.2 * (.25 + .75 * length / max(1, avg)))
        if score > 0:
            scored.append((score, i))
    scored.sort(reverse=True)
    if not scored:
        return {"answer": "I couldn't find enough information in the selected uploaded document(s) to answer this reliably.", "citations": [], "mode": "refusal"}
    top = [corpus[i] | {"score": round(s, 3), "chunk_id": i + 1} for s, i in scored[:4]]
    citations = [{"document": c["doc"], "page": c["page"], "snippet": c["text"][:600], "score": c["score"], "chunk_id": c["chunk_id"]} for c in top]
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        context = "\n\n".join(f"[SOURCE {i+1}: {c['doc']}, page {c['page'] or 'N/A'}]\n{c['text']}" for i, c in enumerate(top))
        prompt = f"You are a strictly document-grounded assistant. Answer ONLY from the SOURCE excerpts below. If they do not answer the question, respond exactly: I couldn't find enough information in the selected uploaded document(s) to answer this reliably. Never invent facts. Cite each relevant statement using [Source 1], [Source 2], etc.\n\n{context}\n\nQUESTION: {q.question}"
        try:
            model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", headers={"x-goog-api-key": key}, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1}}, timeout=35)
            r.raise_for_status()
            answer = "\n".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
            return {"answer": answer, "citations": citations, "mode": "gemini"}
        except Exception as e:
            logger.warning("Gemini generation failed: %s", e)
            return {"answer": "Gemini generation failed. Check API key, model, quota or network. Retrieved excerpts are shown below.", "citations": citations, "mode": "generation_error"}
    return {"answer": "Relevant passages found in your document. Configure GEMINI_API_KEY to generate a synthesized answer.\n\n" + "\n\n".join(f"[Source {i+1}] {c['text'][:500]}" for i, c in enumerate(top[:2])), "citations": citations, "mode": "extractive"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
