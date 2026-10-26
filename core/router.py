import json
from llm.registry import LLMRegistry


KEYWORD_RULES = {
    "ask_about_folder": ["что в папке", "что находится в папке", "расскажи про папку", "расскажи о папке", "обзор папки", "вопрос по папке", "найди в папке", "краткое содержание папки"],
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


FOLDER_VERBS = [
    "расскажи", "обзор", "покажи", "что в", "что находится",
    "проанализ", "кратко", "опиши", "дай обзор", "перескажи",
]


INDEX_VERBS = [
    "индексируй", "проиндексируй", "проиндексир",
]


SORT_VERBS = [
    "отсортируй", "разложи", "сортировк", "классифиц",
]


class IntentRouter:
    def __init__(self, registry: LLMRegistry, config: dict):
        self.registry = registry
        self.router_config = config.get("router", {})
        self.dangerous_tools = list(self.router_config.get("dangerous_tools", []))
        self.use_llm = self.router_config.get("use_llm_for_ambiguous", True)
        self.plugins = {}

    def attach_plugins(self, plugins: dict):
        self.plugins = plugins
        for name, plugin in plugins.items():
            if getattr(plugin, "dangerous", False) and name not in self.dangerous_tools:
                self.dangerous_tools.append(name)

    def get_keyword_rules(self) -> dict:
        rules = dict(KEYWORD_RULES)
        for name, plugin in self.plugins.items():
            if plugin.keywords:
                rules[name] = [kw.lower() for kw in plugin.keywords]
        return rules

    def classify(self, user_text: str) -> dict:
        text = user_text.lower()

        # === ПРИОРИТЕТ 1: если упомянута папка + вопрос-глагол → ask_about_folder
        has_folder = "папк" in text or "каталог" in text
        has_folder_verb = any(v in text for v in FOLDER_VERBS)
        is_explicit_command = (
            any(v in text for v in INDEX_VERBS)
            or any(v in text for v in SORT_VERBS)
            or "резюме папки" in text
            or "резюме всех файлов" in text
        )
        if has_folder and has_folder_verb and not is_explicit_command:
            return {
                "tools": ["ask_about_folder"],
                "reasoning": "Упоминание папки + вопрос (приоритет)",
                "ambiguous": False
            }

        rules = self.get_keyword_rules()
        matched = []
        for tool, keywords in rules.items():
            if any(kw in text for kw in keywords):
                matched.append(tool)

        if matched:
            return {
                "tools": matched,
                "reasoning": "Совпадение по ключевым словам: " + str(matched),
                "ambiguous": False
            }

        if self.use_llm:
            return self._classify_with_llm(user_text, rules)

        return {
            "tools": ["ask_question"],
            "reasoning": "По умолчанию: RAG-поиск по документам",
            "ambiguous": True
        }

    def _classify_with_llm(self, user_text: str, rules: dict) -> dict:
        tools_desc = "\n".join([f"- {t}" for t in rules.keys()])
        prompt = (
            "Ты - классификатор намерений. Доступные инструменты:\n" + tools_desc + "\n"
            "- ask_question: вопросы по проиндексированным документам\n\n"
            "Запрос: \"" + user_text + "\"\n\n"
            "Верни ТОЛЬКО JSON: {\"tools\": [\"имя\"], \"reasoning\": \"...\"}"
        )
        raw = self.registry.generate_with_fallback("default_model", prompt)
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            data["ambiguous"] = False
            return data
        except Exception:
            return {
                "tools": ["ask_question"],
                "reasoning": "LLM не дал JSON. Fallback на RAG.",
                "ambiguous": True
            }