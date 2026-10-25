# Local AI Agent for Russian Text Checking

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
