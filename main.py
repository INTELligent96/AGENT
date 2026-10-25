"""CLI for local AI agent."""
import asyncio
import logging
import os
from pathlib import Path

import typer

import deps
from config import config
from audit import AuditLog
from providers.deepseek_web import DeepSeekWebProvider, MockProvider
from extractors.txt import extract_txt
from extractors.pdf import extract_pdf
from extractors.docx import extract_docx
from extractors.excel import extract_excel
from extractors.image import ocr_image_tesseract
from tasks.russian_check import check_russian_text
from utils.chat_state import ChatState

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
        deps.ensure_group("excel")
        return extract_excel(path)
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"):
        deps.ensure_group("ocr")
        return ocr_image_tesseract(path)
    raise ValueError("Unsupported format: %s" % ext)


def make_provider(mock: bool, force_new_chat: bool = False):
    if mock:
        return MockProvider()
    deps.ensure_group("deepseek")
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


@app.command()
def check(
    file: str = typer.Argument(..., help="Path to file"),
    mock: bool = typer.Option(False, "--mock", help="Use Mock provider"),
    new_chat: bool = typer.Option(
        False, "--new-chat",
        help="Force start of a new chat (ignore existing state)",
    ),
):
    """Check Russian text in a file."""
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

    provider = make_provider(mock, force_new_chat=new_chat)
    result = asyncio.run(
        check_russian_text(provider, text, file_hint=str(path))
    )
    typer.echo(result)

    AuditLog(config.log_path).log(
        str(path), "mock" if mock else "deepseek-web", len(text)
    )


@app.command()
def process(
    directory: str = typer.Argument(..., help="Directory with files"),
    mock: bool = typer.Option(False, "--mock"),
    new_chat: bool = typer.Option(
        False, "--new-chat",
        help="Reset chat state once before batch (all files in one new chat)",
    ),
):
    """Batch-process all supported files in a directory."""
    setup_logging()
    d = Path(directory)
    if not d.is_dir():
        typer.echo("Not a directory: %s" % d, err=True)
        raise typer.Exit(1)

    if new_chat and not mock:
        state_path = os.getenv(
            "DEEPSEEK_CHAT_STATE_PATH", "./deepseek_chat_state.json"
        )
        ChatState.load(Path(state_path)).reset()
        typer.echo("Chat state reset. All files in this batch share one new chat.")

    supported = {
        ".txt", ".pdf", ".docx", ".xls", ".xlsx", ".xlsb", ".csv",
        ".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp",
    }
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix.lower() in supported:
            try:
                check(str(f), mock=mock, new_chat=False)
            except Exception as e:
                typer.echo("Error %s: %s" % (f.name, e), err=True)


@app.command()
def extract(file: str = typer.Argument(...)):
    """Extract text only, without sending to DeepSeek."""
    setup_logging()
    text = extract_text(Path(file))
    typer.echo(text[:2000] + ("..." if len(text) > 2000 else ""))


chat_app = typer.Typer(help="Manage DeepSeek chat state")
app.add_typer(chat_app, name="chat")


@chat_app.command("show")
def chat_show():
    """Show current chat state."""
    state_path = os.getenv(
        "DEEPSEEK_CHAT_STATE_PATH", "./deepseek_chat_state.json"
    )
    state = ChatState.load(Path(state_path))
    typer.echo(state.summary())


@chat_app.command("reset")
def chat_reset():
    """Reset chat state (next request starts a new chat)."""
    state_path = os.getenv(
        "DEEPSEEK_CHAT_STATE_PATH", "./deepseek_chat_state.json"
    )
    state = ChatState.load(Path(state_path))
    state.reset()
    typer.echo("Chat state reset.")


@app.command()
def install(package: str = typer.Argument(..., help="PyPI package name")):
    """Install a package via pip."""
    ok = deps.pip_install([package])
    typer.echo("OK" if ok else "FAILED")


@app.command()
def doctor():
    """Check that all required dependencies are present."""
    missing = deps.check_required()
    if not missing:
        typer.echo("All required modules OK.")
        return
    typer.echo("Missing modules: " + ", ".join(missing))
    if typer.confirm("Install them now?", default=True):
        for m in missing:
            deps.ensure(m)
        typer.echo("Done. Re-run your command.")


if __name__ == "__main__":
    app()