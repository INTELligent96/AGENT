from pathlib import Path
from .indexer import RAGIndexer
from llm.registry import LLMRegistry


class RAGQuestionAnswerer:
    def __init__(self, config: dict, tools_config: dict, registry: LLMRegistry):
        self.indexer = RAGIndexer(config, tools_config)
        self.registry = registry

    def ask(self, question: str, history=None) -> str:
        print("Поиск по базе для вопроса: '" + question[:60] + "'...")
        context_chunks = self.indexer.search(question, top_k=5)

        if not context_chunks:
            return "В базе данных не найдено информации по этому вопросу."

        context_text = ""
        for i, chunk in enumerate(context_chunks, 1):
            source = Path(chunk['source']).name
            context_text += "--- Фрагмент " + str(i) + " (Источник: " + source + ", часть " + str(chunk['chunk_id']) + ") ---\n"
            context_text += chunk['text'] + "\n\n"

        system_prompt = (
            "Ты - ассистент по работе с документами. Отвечай на вопрос пользователя, "
            "ОПИРАЯСЬ ТОЛЬКО на предоставленные фрагменты текста. "
            "Если в тексте нет ответа, честно скажи, что не знаешь. "
            "Обязательно указывай, из какого файла взята информация. "
            "Отвечай кратко и по делу."
        )

        user_prompt = ""
        if history:
            user_prompt += "ИСТОРИЯ ДИАЛОГА (для понимания контекста):\n"
            for h in history[-6:]:
                role = "Пользователь" if h["role"] == "user" else "Ассистент"
                content = str(h["content"])[:300]
                user_prompt += role + ": " + content + "\n"
            user_prompt += "\n"

        user_prompt += "КОНТЕКСТ:\n" + context_text + "\n\nВОПРОС: " + question

        print("Запуск отказоустойчивой генерации (complex_reasoning)...")
        return self.registry.generate_with_fallback("complex_reasoning", user_prompt, system_prompt)