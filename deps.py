"""Self-healing dependency manager for the agent."""
import importlib
import subprocess
import sys
from typing import Iterable, List, Optional

PACKAGE_ALIASES = {
    "docx": "python-docx",
    "PIL": "Pillow",
    "free_deepseek_api": "free-deepseek-api",
    "excelreader_native": "excelreader-native",
    "multipart": "python-multipart",
    "pytesseract": "pytesseract",
    "dotenv": "python-dotenv",
}

REQUIRED = [
    "typer",
    "dotenv",
    "pypdf",
    "docx",
    "PIL",
    "fastapi",
    "uvicorn",
    "multipart",
]

OPTIONAL = {
    "excel": ["excelreader_native"],
    "ocr": ["pytesseract"],
    "deepseek": ["free_deepseek_api"],
}


def is_installed(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


def pip_install(packages: Iterable[str], quiet: bool = False) -> bool:
    pkgs = list(packages)
    if not pkgs:
        return True
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    if quiet:
        cmd.append("-q")
    print("[deps] Installing: " + " ".join(pkgs))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[deps] Failed to install: " + " ".join(pkgs))
        return False
    importlib.invalidate_caches()
    return True


def ensure(
    module_name: str,
    package_name: Optional[str] = None,
    quiet: bool = False,
) -> bool:
    if is_installed(module_name):
        return True
    pkg = package_name or PACKAGE_ALIASES.get(module_name, module_name)
    return pip_install([pkg], quiet=quiet)


def ensure_group(group: str) -> bool:
    modules = OPTIONAL.get(group, [])
    missing = [m for m in modules if not is_installed(m)]
    if not missing:
        return True
    packages = [PACKAGE_ALIASES.get(m, m) for m in missing]
    return pip_install(packages)


def check_required() -> List[str]:
    return [m for m in REQUIRED if not is_installed(m)]