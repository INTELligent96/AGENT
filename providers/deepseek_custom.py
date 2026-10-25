"""Custom Playwright client with persistent profile, stealth, and manual intervention."""
import asyncio
import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page

try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

logger = logging.getLogger(__name__)

INPUT_SELECTORS = [
    "#chat-input",
    'textarea[placeholder*="Send a message"]',
    'textarea[data-testid="chat-input"]',
    'div[contenteditable][role="textbox"]',
    "textarea",
]

RESPONSE_SELECTORS = [
    ".ds-markdown.ds-markdown--block",
    ".ds-assistant-message-main-content",
    'div[class*="f9bf7997"]',
]

HUMAN_VERIFICATION_TEXTS = [
    "verify you are human",
    "checking your browser",
    "human verification",
    "подтвердите, что вы человек",
]


class DeepSeekSessionExpired(RuntimeError):
    pass


class CustomDeepSeekClient:
    def __init__(
        self,
        user_data_dir: str = "./deepseek_profile",
        headless: bool = False,
        chat_url: Optional[str] = None,
    ) -> None:
        self.user_data_dir = str(Path(user_data_dir).resolve())
        self.headless = headless
        self.chat_url = chat_url
        self.last_url: Optional[str] = None

    async def _is_human_verification(self, page: Page) -> bool:
        try:
            content = (await page.content()).lower()
            for text in HUMAN_VERIFICATION_TEXTS:
                if text in content:
                    return True
        except Exception:
            pass
        if any(x in page.url.lower() for x in ["challenge", "verify", "captcha"]):
            return True
        return False

    async def _wait_for_human(self, page: Page) -> None:
        logger.warning(
            "Обнаружена проверка на человека. Пройдите её в открытом окне "
            "браузера, затем нажмите Enter в консоли."
        )
        await asyncio.to_thread(
            input, ">>> Нажмите Enter после прохождения проверки... "
        )
        logger.info("Продолжаем работу после ручного вмешательства.")

    async def _find_input(self, page: Page) -> Optional[str]:
        for sel in INPUT_SELECTORS:
            try:
                el = await page.wait_for_selector(sel, timeout=5000)
                if el:
                    logger.info("Found input with selector: %s", sel)
                    return sel
            except Exception:
                continue
        return None

    async def _find_response_selector(self, page: Page) -> Optional[str]:
        for sel in RESPONSE_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=10000)
                return sel
            except Exception:
                continue
        return None

    async def ask(self, prompt: str) -> str:
        if Stealth is None:
            raise RuntimeError(
                "playwright-stealth not installed. "
                "Run: pip install playwright-stealth"
            )

        self.last_url = None

        async with Stealth().use_async(async_playwright()) as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
                viewport={"width": 1280, "height": 800},
            )

            page = await context.new_page()
            try:
                from playwright_stealth import stealth_async
                await stealth_async(page)
            except Exception:
                pass

            try:
                await page.goto(
                    "https://chat.deepseek.com",
                    wait_until="networkidle",
                    timeout=30000,
                )

                if await self._is_human_verification(page):
                    await self._wait_for_human(page)

                if self.chat_url:
                    logger.info("Opening existing chat: %s", self.chat_url)
                    await page.goto(
                        self.chat_url,
                        wait_until="networkidle",
                        timeout=30000,
                    )

                input_sel = await self._find_input(page)
                if not input_sel:
                    if await self._is_human_verification(page):
                        await self._wait_for_human(page)
                        input_sel = await self._find_input(page)
                    if not input_sel:
                        raise DeepSeekSessionExpired(
                            "Не удалось найти поле ввода. Возможно, сессия истекла. "
                            "Удалите папку deepseek_profile для ручного входа."
                        )

                await page.fill(input_sel, prompt)
                await page.keyboard.press("Enter")
                logger.info("Prompt sent, waiting for response...")

                resp_sel = await self._find_response_selector(page)
                if not resp_sel:
                    raise RuntimeError(
                        "Не удалось найти блок ответа. DeepSeek изменил вёрстку?"
                    )

                await asyncio.sleep(2)
                elements = await page.query_selector_all(resp_sel)
                if not elements:
                    raise RuntimeError("Ответ не найден")

                text = await elements[-1].inner_text()
                self.last_url = page.url
                logger.info(
                    "Received response: %d chars, url=%s",
                    len(text), self.last_url,
                )
                return text.strip()

            finally:
                await context.close()