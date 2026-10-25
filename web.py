"""FastAPI web interface for local agent."""
import logging
import os
import shutil
import tempfile
import traceback
from pathlib import Path

import deps

deps.ensure("multipart", "python-multipart")

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse

from config import config
from providers.deepseek_web import DeepSeekWebProvider
from tasks.russian_check import check_russian_text
from extractors.txt import extract_txt
from extractors.pdf import extract_pdf
from extractors.docx import extract_docx
from extractors.excel import extract_excel
from extractors.image import ocr_image_tesseract
from utils.chat_state import ChatState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("web")

app = FastAPI(title="Local AI Agent")

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Local AI Agent</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 1rem; }
h1 { font-size: 1.5rem; }
button { padding: 0.6rem 1.4rem; font-size: 1rem; cursor: pointer; background: #2563eb; color: white; border: none; border-radius: 6px; }
button:disabled { background: #94a3b8; cursor: not-allowed; }
.result { background: #f4f4f4; padding: 1rem; border-radius: 6px; white-space: pre-wrap; margin-top: 1rem; font-family: monospace; font-size: 0.9rem; }
.result.error { background: #fee2e2; color: #991b1b; }
.loading { color: #666; margin-top: 1rem; }
input[type=file] { margin: 0.5rem 0; }
.note { color: #666; font-size: 0.9rem; margin-top: 0.5rem; }
.chat-info { background: #eff6ff; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.85rem; margin: 0.5rem 0; font-family: monospace; }
label { display: block; margin: 0.4rem 0; font-size: 0.9rem; }
</style>
</head>
<body>
<h1>Local AI Agent</h1>
<p>Upload a file - the agent will check Russian text.</p>
<p class="note">First run opens a browser window. If you see a human verification, complete it and press Enter in the console.</p>
<div id="chat-info" class="chat-info" style="display:none"></div>
<form id="form" enctype="multipart/form-data">
<input type="file" name="file" required>
<label><input type="checkbox" name="new_chat" value="true"> Start new chat (ignore current context)</label>
<button type="submit" id="submit">Check</button>
</form>
<div id="status" class="loading"></div>
<div id="result" class="result" style="display:none"></div>
<script>
async function refreshChatInfo() {
  try {
    const r = await fetch('/chat/state');
    const data = await r.json();
    const el = document.getElementById('chat-info');
    if (data.chat_url) {
      el.style.display = 'block';
      el.textContent = 'Current chat: ' + data.chat_url +
        ' | messages: ' + data.message_count +
        ' | age: ' + data.age_hours.toFixed(1) + 'h';
    } else {
      el.style.display = 'none';
    }
  } catch (e) {}
}
refreshChatInfo();

document.getElementById('form').onsubmit = async (e) => {
  e.preventDefault();
  const status = document.getElementById('status');
  const result = document.getElementById('result');
  const submit = document.getElementById('submit');
  status.textContent = 'Processing... (may take up to 60 sec; check the browser window if it opens)';
  result.style.display = 'none';
  result.classList.remove('error');
  submit.disabled = true;
  try {
    const fd = new FormData(e.target);
    const r = await fetch('/check', { method: 'POST', body: fd });
    const data = await r.json();
    status.textContent = '';
    result.style.display = 'block';
    if (data.error) {
      result.classList.add('error');
      result.textContent = 'ERROR: ' + data.error;
    } else if (data.result && data.result.length > 0) {
      result.textContent = data.result;
    } else {
      result.classList.add('error');
      result.textContent = 'Server returned empty result. Check uvicorn console for logs.';
    }
    refreshChatInfo();
  } catch (err) {
    status.textContent = '';
    result.style.display = 'block';
    result.classList.add('error');
    result.textContent = 'Network error: ' + err;
  } finally {
    submit.disabled = false;
  }
};
</script>
</body></html>"""


def extract_by_ext(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return extract_txt(path)
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext in (".xls", ".xlsx", ".xlsb", ".csv"):
        deps.ensure_group("excel")
        return extract_excel(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"):
        deps.ensure_group("ocr")
        return ocr_image_tesseract(path)
    raise ValueError("Unsupported format: %s" % ext)


def _make_provider(force_new_chat: bool = False) -> DeepSeekWebProvider:
    return DeepSeekWebProvider(
        user_data_dir=os.getenv("DEEPSEEK_USER_DATA_DIR", "./deepseek_profile"),
        state_path=os.getenv(
            "DEEPSEEK_CHAT_STATE_PATH", "./deepseek_chat_state.json"
        ),
        max_age_hours=float(os.getenv("DEEPSEEK_MAX_AGE_HOURS", "24")),
        max_messages=int(os.getenv("DEEPSEEK_MAX_MESSAGES", "30")),
        rotate_on_file_type_change=os.getenv(
            "DEEPSEEK_ROTATE_ON_FILE_TYPE_CHANGE", "false"
        ).lower() == "true",
        force_new_chat=force_new_chat,
        headless=os.getenv("DEEPSEEK_HEADLESS", "false").lower() == "true",
        chat_url=os.getenv("DEEPSEEK_CHAT_URL") or None,
    )


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.get("/chat/state")
def chat_state():
    state_path = os.getenv(
        "DEEPSEEK_CHAT_STATE_PATH", "./deepseek_chat_state.json"
    )
    state = ChatState.load(Path(state_path))
    return {
        "chat_url": state.chat_url,
        "message_count": state.message_count,
        "last_file": state.last_file,
        "age_hours": state.age_hours(),
    }


@app.post("/check")
async def check(
    file: UploadFile = File(...),
    new_chat: bool = Form(False),
):
    tmpdir = Path(tempfile.mkdtemp())
    tmp = tmpdir / (file.filename or "upload.bin")
    try:
        with tmp.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info("Received file: %s (%d bytes)", tmp.name, tmp.stat().st_size)

        text = extract_by_ext(tmp)
        logger.info("Extracted %d chars", len(text))

        deps.ensure_group("deepseek")
        provider = _make_provider(force_new_chat=new_chat)
        result = await check_russian_text(
            provider, text, file_hint=file.filename or tmp.name
        )

        logger.info(
            "Result: type=%s, preview=%r",
            type(result).__name__,
            (result[:120] if result else None),
        )
        if not result or not result.strip():
            return {"error": "Empty response from provider. Check uvicorn logs."}
        return {"result": result}

    except Exception as e:
        logger.error("Request failed: %s\n%s", e, traceback.format_exc())
        return {"error": "%s: %s" % (type(e).__name__, e)}
    finally:
        tmp.unlink(missing_ok=True)
        try:
            tmpdir.rmdir()
        except OSError:
            pass