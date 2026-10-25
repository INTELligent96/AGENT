"""Provider DeepSeek via custom Playwright client with chat state management."""
import logging
from pathlib import Path
from typing import Optional

from utils.throttle import HumanLikeThrottle
from utils.chat_state import ChatState
from .deepseek_custom import CustomDeepSeekClient, DeepSeekSessionExpired

logger = logging.getLogger(__name__)


class DeepSeekWebProvider:
    def __init__(
        self,
        user_data_dir: str = "./deepseek_profile",
        state_path: str = "./deepseek_chat_state.json",
        max_age_hours: float = 24.0,
        max_messages: int = 30,
        rotate_on_file_type_change: bool = False,
        force_new_chat: bool = False,
        headless: bool = False,
        chat_url: Optional[str] = None,
        thinking: bool = False,
    ) -> None:
        self.user_data_dir = user_data_dir
        self.state_path = Path(state_path)
        self.max_age_hours = max_age_hours
        self.max_messages = max_messages
        self.rotate_on_file_type_change = rotate_on_file_type_change
        self.force_new_chat = force_new_chat
        self.headless = headless
        self.chat_url = chat_url
        self.throttle = HumanLikeThrottle()
        self.state = ChatState.load(self.state_path)

    async def ask(self, prompt: str, file_hint: Optional[str] = None) -> str:
        await self.throttle.wait_before_request()

        rotate, reason = self.state.should_rotate(
            new_file=file_hint,
            max_age_hours=self.max_age_hours,
            max_messages=self.max_messages,
            force_new=self.force_new_chat,
            rotate_on_file_type_change=self.rotate_on_file_type_change,
        )
        if rotate:
            logger.info("Rotating chat: %s", reason)
            self.state.reset()
            target_url = self.chat_url
        else:
            logger.info("Chat decision: %s", reason)
            target_url = self.chat_url or self.state.chat_url

        client = CustomDeepSeekClient(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            chat_url=target_url,
        )
        await self.throttle.typing_pause()

        try:
            result = await client.ask(prompt)
        except DeepSeekSessionExpired as e:
            raise RuntimeError(
                "%s\n\n"
                "Если открылось окно браузера, войдите в аккаунт вручную. "
                "После входа нажмите Enter в консоли." % e
            ) from e

        self.state.record_ask(file=file_hint, new_url=client.last_url)
        logger.info(
            "State updated: url=%s msgs=%d",
            self.state.chat_url, self.state.message_count,
        )
        return result


class MockProvider:
    def __init__(self) -> None:
        self.throttle = HumanLikeThrottle()

    async def ask(self, prompt: str, file_hint: Optional[str] = None) -> str:
        await self.throttle.wait_before_request()
        await self.throttle.typing_pause()
        preview = prompt[:80]
        hint = " [file=%s]" % file_hint if file_hint else ""
        return "[MOCK%s] Got %d chars. Preview: %s..." % (
            hint, len(prompt), preview
        )