import json
from llm.registry import LLMRegistry

KEYWORD_RULES = {
    "generate_code": ["напиши код", "напиши функцию", "напиши скрипт", "сгенерируй код", "python код", "код на питоне", "напиши программу"],
    "check_spelling": ["проверь ошибки", "орфография", "исправь ошибки", "пунктуация", "опечатки"],
    "summarize_file": ["сделай резюме", "краткое содержание", "о чём документ", "о чем документ", "перескажи"],
    "batch_summarize": ["резюме папки", "резюме всех файлов", "резюме всей папки"],
    "classify_files": ["отсортируй файлы", "разложи по папкам", "классифицируй"],
    "make_file_list": ["список файлов", "перечень файлов"],
    "make_excel_chart": ["построй график", "сделай график", "график в excel", "диаграмма"],
    "web_search": ["найди в интернете", "погугли", "поищи в сети", "поиск в интернете"],
    "process_long_doc": ["полный разбор", "разбери книгу", "разбери документ целиком"],
    "index_folder": ["проиндексируй", "индексируй папку"],
    "translate": ["переведи", "перевод на", "translate"],
    "open_style_studio": ["студия стилей", "замени стили", "сопоставь стили", "стили word"],
}

class IntentRouter:
    def __init__(self, registry: LLMRegistry, config: dict):
        self.registry = registry
        self.router_config = config.get("router", {})
        self.dangerous_tools = self.router_config.get("dangerous_tools", [])
        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)

    def classify(self, user_text: str) -> dict:
        """Возвращает {tools: [...], reasoning: str, ambiguous: bool}"""
        text = user_text.lower()

        # 1. Быстрая проверка по ключевым словам
        matched = []
        for tool, keywords in KEYWORD_RULES.items():
            if any(kw in text for kw in keywords):
                matched.append(tool)

        if matched:
            return {
                "tools": matched,
                "reasoning": f"Совпадение по ключевым словам: {matched}",
                "ambiguous": False
            }

        # 2. Если ничего не нашли — спрашиваем LLM (если включено)
        if self.use_llm:
            return self._classify_with_llm(user_text)

        # 3. По умолчанию — RAG
        return {
            "tools": ["ask_question"],
            "reasoning": "По умолчанию: RAG-поиск по документам",
            "ambiguous": True
        }

    def _classify_with_llm(self, user_text: str) -> dict:
        tools_desc = "\n".join([f"- {t}: {', '.join(kw[:2])}" for t, kw in KEYWORD_RULES.items()])
        prompt = f"""Ты — классификатор намерений пользователя в системе документооборота.
Доступные инструменты:
{tools_desc}
- ask_question: вопросы по проиндексированным документам (RAG)

Запрос пользователя: "{user_text}"

Верни ТОЛЬКО валидный JSON без markdown:
{{"tools": ["имя_инструмента"], "reasoning": "кратко почему"}}

Если запрос — вопрос по документам, верни ["ask_question"].
Если хочешь вызвать несколько инструментов — перечисли их в списке.
"""
        raw = self.registry.generate_with_fallback("default_model", prompt)
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            data["ambiguous"] = False
            return data
        except Exception:
            return {
                "tools": ["ask_question"],
                "reasoning": f"LLM не дал валидный JSON, fallback на RAG. Сырой ответ: {raw[:100]}",
                "ambiguous": True
            }
