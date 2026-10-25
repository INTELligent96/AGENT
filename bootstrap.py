#cd /d D:\DEEPSEEK\AGENT

#!/usr/bin/env python3
"""Bootstrap: creates project structure for local AI agent. Python 3.10+."""
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

FILES = {}

FILES["requirements.txt"] = r'''free-deepseek-api
playwright
pypdf
python-docx
excelreader-native
pyexcel
xlrd
openpyxl
Pillow
pytesseract
typer
fastapi
uvicorn
python-dotenv
pytest
pytest-asyncio
'''

FILES["pytest.ini"] = r'''[pytest]
asyncio_mode = auto
'''

FILES[".env.example"] = r'''DEEPSEEK_AUTH_PATH=auth.json
ALLOWED_DIRS=.
AUDIT_LOG=audit.log
DEEPSEEK_THINKING=false
'''

FILES[".gitignore"] = r'''__pycache__/
*.pyc
.env
auth.json
audit.log
.venv/
venv/
.pytest_cache/
'''

FILES["utils/__init__.py"] = ""

FILES["utils/throttle.py"] = r'''
"""Randomized delays imitating human behavior."""
import asyncio
import random
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class HumanLikeThrottle:
    """Manages delays between requests to DeepSeek web chat."""

    def __init__(
        self,
        short_range: Tuple[float, float] = (8.0, 22.0),
        long_range: Tuple[float, float] = (45.0, 75.0),
        batch_size: int = 4,
    ) -> None:
        self.short_range = short_range
        self.long_range = long_range
        self.batch_size = batch_size
        self._counter = 0

    async def wait_before_request(self) -> None:
        self._counter += 1
        if self._counter % self.batch_size == 0:
            delay = random.uniform(*self.long_range)
            logger.info("Long pause %.1fs after %d requests", delay, self._counter)
        else:
            delay = random.uniform(*self.short_range)
            logger.debug("Short pause %.1fs before request #%d", delay, self._counter)
        await asyncio.sleep(delay)

    async def typing_pause(self) -> None:
        delay = random.uniform(1.2, 3.8)
        await asyncio.sleep(delay)

    def reset(self) -> None:
        self._counter = 0
'''

FILES["config.py"] = r'''
"""Configuration from .env."""
import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

load_dotenv()

_SEP = ";" if os.name == "nt" else ":"


class Config:
    def __init__(self) -> None:
        self.auth_path = Path(os.getenv("DEEPSEEK_AUTH_PATH", "auth.json"))
        allowed = os.getenv("ALLOWED_DIRS", ".")
        self.allowed_dirs: List[Path] = [
            Path(p.strip()).expanduser().resolve()
            for p in allowed.split(_SEP)
            if p.strip()
        ]
        self.log_path = Path(os.getenv("AUDIT_LOG", "audit.log"))
        self.thinking = os.getenv("DEEPSEEK_THINKING", "false").lower() == "true"

    def is_allowed(self, path: Path) -> bool:
        try:
            p = path.expanduser().resolve()
        except Exception:
            return False
        for d in self.allowed_dirs:
            if p == d:
                return True
            try:
                p.relative_to(d)
                return True
            except ValueError:
                continue
        return False


config = Config()
'''

FILES["audit.py"] = r'''
"""Logging of LLM calls (metadata only)."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        file: str,
        provider: str,
        fragment_length: int,
        request_id: Optional[str] = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": file,
            "provider": provider,
            "fragment_length": fragment_length,
            "request_id": request_id,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
'''

FILES["providers/__init__.py"] = ""

FILES["providers/deepseek_web.py"] = r'''
"""Provider DeepSeek via web chat (free-deepseek-api)."""
import asyncio
import logging
from utils.throttle import HumanLikeThrottle

logger = logging.getLogger(__name__)


class DeepSeekWebProvider:
    """Wrapper over free-deepseek-api with throttling and retry."""

    def __init__(self, auth_path: str, thinking: bool = False) -> None:
        self.auth_path = str(auth_path)
        self.thinking = thinking
        self.throttle = HumanLikeThrottle()

    async def ask(self, prompt: str) -> str:
        await self.throttle.wait_before_request()

        try:
            from free_deepseek_api import DeepSeekClient
        except ImportError as e:
            raise RuntimeError(
                "free-deepseek-api not installed. Run: "
                "pip install free-deepseek-api && playwright install chromium"
            ) from e

        async with DeepSeekClient(auth_path=self.auth_path) as client:
            if hasattr(client, "set_thinking"):
                try:
                    await client.set_thinking(self.thinking)
                except Exception as e:
                    logger.warning("set_thinking failed: %s", e)

            await self.throttle.typing_pause()

            for attempt in range(1, 4):
                try:
                    return await client.ask(prompt)
                except Exception as e:
                    logger.error("ask() attempt %d failed: %s", attempt, e)
                    if attempt == 3:
                        raise
                    backoff = 60 * (2 ** (attempt - 1))
                    logger.info("Retry in %ds...", backoff)
                    await asyncio.sleep(backoff)
            return ""


class MockProvider:
    """Stub for tests and dry-run."""

    def __init__(self) -> None:
        self.throttle = HumanLikeThrottle()

    async def ask(self, prompt: str) -> str:
        await self.throttle.wait_before_request()
        await self.throttle.typing_pause()
        preview = prompt[:80]
        return "[MOCK] Got %d chars. Preview: %s..." % (len(prompt), preview)
'''

FILES["extractors/__init__.py"] = ""

FILES["extractors/txt.py"] = r'''
from pathlib import Path


def extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")
'''

FILES["extractors/pdf.py"] = r'''
from pathlib import Path


def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)
'''

FILES["extractors/docx.py"] = r'''
from pathlib import Path


def extract_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
'''

FILES["extractors/excel.py"] = r'''
"""Read XLS/XLSX/XLSB/CSV with format detection by signature."""
from pathlib import Path


def _sniff(path: Path) -> str:
    sig = path.read_bytes()[:8]
    if sig.startswith(b"PK"):
        return "xlsx"
    if sig.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls"
    return "unknown"


def extract_excel(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return path.read_text(encoding="utf-8", errors="replace")

    try:
        from excelreader_native import open_workbook
        wb = open_workbook(str(path))
        lines = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            lines.append("### Sheet: " + sheet)
            for row in ws.iter_rows(values_only=True):
                lines.append("\t".join("" if c is None else str(c) for c in row))
        return "\n".join(lines)
    except Exception as e:
        try:
            import pyexcel as p
            sheet = p.get_array(file_name=str(path))
            return "\n".join("\t".join(str(c) for c in row) for row in sheet)
        except Exception as e2:
            raise RuntimeError(
                "Could not read Excel %s: %s / %s" % (path, e, e2)
            )
'''

FILES["extractors/image.py"] = r'''
"""Image handling: base64 and local OCR."""
import base64
import io
from pathlib import Path


def prepare_image(path: Path, max_size: int = 1600) -> str:
    from PIL import Image
    img = Image.open(path)
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    fmt = "JPEG" if img.mode in ("RGB", "L") else "PNG"
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()


def ocr_image_tesseract(path: Path, lang: str = "rus+eng") -> str:
    try:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(path), lang=lang)
    except Exception as e:
        return "[OCR unavailable: %s]" % e
'''

FILES["tasks/__init__.py"] = ""

FILES["tasks/russian_check.py"] = r'''
"""Russian text check scenario."""
import logging

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = (
    "Check the spelling, punctuation, and style of the following Russian text.\n"
    "Return the corrected text and a brief list of edits (no more than 5 items).\n\n"
    "Text:\n{text}\n"
)


async def check_russian_text(provider, text: str) -> str:
    if not text or not text.strip():
        return "[Empty text - nothing to check]"
    prompt = PROMPT_TEMPLATE.format(text=text)
    return await provider.ask(prompt)
'''

FILES["main.py"] = r'''
"""CLI for local AI agent."""
import asyncio
import logging
from pathlib import Path

import typer

from config import config
from audit import AuditLog
from providers.deepseek_web import DeepSeekWebProvider, MockProvider
from extractors.txt import extract_txt
from extractors.pdf import extract_pdf
from extractors.docx import extract_docx
from extractors.excel import extract_excel
from extractors.image import ocr_image_tesseract
from tasks.russian_check import check_russian_text

app = typer.Typer(help="Local AI agent for Russian text checking")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return extract_txt(path)
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext in (".xls", ".xlsx", ".xlsb", ".csv"):
        return extract_excel(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"):
        return ocr_image_tesseract(path)
    raise ValueError("Unsupported format: %s" % ext)


def make_provider(mock: bool):
    if mock:
        return MockProvider()
    return DeepSeekWebProvider(str(config.auth_path), config.thinking)


@app.command()
def check(
    file: str = typer.Argument(..., help="Path to file"),
    mock: bool = typer.Option(False, "--mock", help="Use Mock provider"),
):
    setup_logging()
    path = Path(file)
    if not path.exists():
        typer.echo("File not found: %s" % path, err=True)
        raise typer.Exit(1)
    if not config.is_allowed(path):
        typer.echo("Access denied: %s" % path, err=True)
        raise typer.Exit(1)

    text = extract_text(path)
    typer.echo("Extracted %d chars from %s" % (len(text), path.name), err=True)

    provider = make_provider(mock)
    result = asyncio.run(check_russian_text(provider, text))
    typer.echo(result)

    AuditLog(config.log_path).log(
        str(path), "mock" if mock else "deepseek-web", len(text)
    )


@app.command()
def process(
    directory: str = typer.Argument(..., help="Directory with files"),
    mock: bool = typer.Option(False, "--mock"),
):
    setup_logging()
    d = Path(directory)
    if not d.is_dir():
        typer.echo("Not a directory: %s" % d, err=True)
        raise typer.Exit(1)

    supported = {
        ".txt", ".pdf", ".docx", ".xls", ".xlsx", ".xlsb", ".csv",
        ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp",
    }
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in supported:
            try:
                check(str(f), mock=mock)
            except Exception as e:
                typer.echo("Error %s: %s" % (f.name, e), err=True)


@app.command()
def extract(file: str = typer.Argument(...)):
    setup_logging()
    text = extract_text(Path(file))
    typer.echo(text[:2000] + ("..." if len(text) > 2000 else ""))


if __name__ == "__main__":
    app()
'''

FILES["web.py"] = r'''
"""FastAPI web interface for local agent."""
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse

from config import config
from providers.deepseek_web import DeepSeekWebProvider
from tasks.russian_check import check_russian_text
from extractors.txt import extract_txt
from extractors.pdf import extract_pdf
from extractors.docx import extract_docx
from extractors.excel import extract_excel
from extractors.image import ocr_image_tesseract

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
.loading { color: #666; margin-top: 1rem; }
input[type=file] { margin: 0.5rem 0; }
</style>
</head>
<body>
<h1>Local AI Agent</h1>
<p>Upload a file - the agent will check Russian text.</p>
<form id="form" enctype="multipart/form-data">
<input type="file" name="file" required>
<button type="submit" id="submit">Check</button>
</form>
<div id="status" class="loading"></div>
<div id="result" class="result" style="display:none"></div>
<script>
document.getElementById('form').onsubmit = async (e) => {
  e.preventDefault();
  const status = document.getElementById('status');
  const result = document.getElementById('result');
  const submit = document.getElementById('submit');
  status.textContent = 'Processing... (8-22 sec pause to imitate human behavior)';
  result.style.display = 'none';
  submit.disabled = true;
  try {
    const fd = new FormData(e.target);
    const r = await fetch('/check', { method: 'POST', body: fd });
    const data = await r.json();
    status.textContent = '';
    result.style.display = 'block';
    result.textContent = data.result || data.error || 'Empty';
  } catch (err) {
    status.textContent = 'Error: ' + err;
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
        return extract_excel(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"):
        return ocr_image_tesseract(path)
    raise ValueError("Unsupported format: %s" % ext)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


@app.post("/check")
async def check(file: UploadFile = File(...)):
    tmpdir = Path(tempfile.mkdtemp())
    tmp = tmpdir / (file.filename or "upload.bin")
    try:
        with tmp.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        text = extract_by_ext(tmp)
        provider = DeepSeekWebProvider(str(config.auth_path), config.thinking)
        result = await check_russian_text(provider, text)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)
        try:
            tmpdir.rmdir()
        except OSError:
            pass
'''

FILES["README.md"] = r'''# Local AI Agent for Russian Text Checking

Uses free-deepseek-api (DeepSeek web chat automation) with randomized delays
to reduce account lockout risk.

## Install

    cd AGENT
    pip install -r requirements.txt
    playwright install chromium
    copy .env.example .env

Edit .env:
- DEEPSEEK_AUTH_PATH - path to auth file
- ALLOWED_DIRS - folders the agent may read (separator ; on Windows)
- DEEPSEEK_THINKING - true/false

## DeepSeek auth

Run once:

    python -m free_deepseek_api.auth

Log in to DeepSeek manually, wait for auth.json to be saved.

## Usage

CLI:

    python main.py check file.txt
    python main.py check file.txt --mock
    python main.py process C:/path/to/folder
    python main.py extract file.pdf

Web:

    uvicorn web:app --reload --port 8000

Open http://localhost:8000

## Supported formats

- Documents: .txt, .pdf, .docx
- Tables: .xls, .xlsx, .xlsb, .csv
- Images: .png, .jpg, .jpeg, .webp, .tiff, .bmp (Tesseract OCR)

## Tests

    pytest tests/ -v

## Security

- Folder whitelist (ALLOWED_DIRS)
- Audit log (audit.log) without content
- Randomized delays: 8-22 sec between requests, 45-75 sec after every 4

## Limitations

free-deepseek-api is an unofficial library. Use may lead to DeepSeek account
lockout. Not for commercial use.
'''

FILES["tests/__init__.py"] = ""

FILES["tests/test_throttle.py"] = r'''
"""Tests for throttling and Mock provider."""
import asyncio
import pytest
from utils.throttle import HumanLikeThrottle


@pytest.mark.asyncio
async def test_throttle_short_range(monkeypatch):
    delays = []
    monkeypatch.setattr("asyncio.sleep", lambda d: delays.append(d) or asyncio.sleep(0))

    t = HumanLikeThrottle(short_range=(8.0, 22.0), batch_size=100)
    for _ in range(3):
        await t.wait_before_request()

    for d in delays:
        assert 8.0 <= d <= 22.0, "Delay %s out of range" % d


@pytest.mark.asyncio
async def test_throttle_long_pause_after_batch(monkeypatch):
    delays = []
    monkeypatch.setattr("asyncio.sleep", lambda d: delays.append(d) or asyncio.sleep(0))

    t = HumanLikeThrottle(short_range=(8.0, 22.0), long_range=(45.0, 75.0), batch_size=4)
    for _ in range(4):
        await t.wait_before_request()

    assert 45.0 <= delays[-1] <= 75.0


@pytest.mark.asyncio
async def test_mock_provider_uses_throttle():
    from providers.deepseek_web import MockProvider
    p = MockProvider()
    p.throttle = HumanLikeThrottle(short_range=(0.001, 0.002), batch_size=100)
    result = await p.ask("test")
    assert result.startswith("[MOCK]")
'''


def main() -> None:
    created = 0
    skipped = 0
    for rel, content in FILES.items():
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        content = content.strip("\n") + "\n"
        p = ROOT / rel
        if p.exists() and p.read_text(encoding="utf-8") == content:
            skipped += 1
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        print("  [write] " + rel)
        created += 1

    print("")
    print("Done: %d files created, %d skipped." % (created, skipped))
    print("")
    print("Next steps:")
    print("  1. pip install -r requirements.txt")
    print("  2. playwright install chromium")
    print("  3. copy .env.example .env")
    print("  4. pytest tests/ -v")
    print("  5. python main.py check tests/test_throttle.py --mock")


if __name__ == "__main__":
    main()