import json
from llm.registry import LLMRegistry

class Critic:
    def __init__(self, registry: LLMRegistry, config: dict):
        self.registry = registry
        cfg = config.get("self_check", {})
        self.enabled = cfg.get("enabled", True)
        self.force_always = cfg.get("force_always", False)
        self.max_retries = cfg.get("max_retries", 2)
        self.min_score = cfg.get("min_score", 8)
        self.critic_model_key = cfg.get("critic_model", "local_logic")
        self.default_critic_key = cfg.get("default_model_for_check", "local_fast")

    def should_check(self, task_type: str) -> bool:
        """Определяет, нужна ли проверка для этого типа задачи."""
        if not self.enabled:
            return False
        if self.force_always:
            return True
        # По умолчанию проверяем только «смысловые» задачи
        return task_type in ["rag", "summarize", "translate", "structure"]

    def check_general(self, task: str, answer: str, task_type: str) -> dict:
        """Универсальная оценка ответа."""
        # Для RAG выбираем умную модель, для остального — быструю
        model_key = self.critic_model_key if task_type == "rag" else self.default_critic_key

        prompt = f"""Ты — строгий критик ответов ИИ.
Задача: {task}
Ответ агента: {answer}

Оцени ответ по трём критериям:
1. Отвечает ли он на задачу? (да/нет)
2. Есть ли галлюцинации / выдуманные факты? (да/нет)
3. Достаточно ли он полон? (да/нет)

Верни ТОЛЬКО JSON без markdown:
{{"score": 1-10, "issues": ["проблема1", "проблема2"], "verdict": "accept" или "retry"}}
"""
        raw = self.registry.generate_with_fallback(model_key, prompt)
        return self._parse(raw)

    def check_factual(self, context: str, answer: str) -> dict:
        """Строгая проверка для RAG: все ли факты подтверждаются контекстом."""
        prompt = f"""Ты — фактчекер. Проверь, все ли утверждения в ответе подтверждаются контекстом.

КОНТЕКСТ:
{context[:6000]}

ОТВЕТ:
{answer}

Верни ТОЛЬКО JSON без markdown:
{{"score": 1-10, "unverified_claims": ["утверждение1"], "verdict": "accept" или "retry"}}
"""
        raw = self.registry.generate_with_fallback(self.critic_model_key, prompt)
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            data.setdefault("score", 5)
            data.setdefault("verdict", "retry")
            data.setdefault("issues", [])
            return data
        except Exception:
            return {"score": 5, "issues": ["Критик вернул невалидный JSON"], "verdict": "retry"}

    def run_with_retry(self, generate_fn, task: str, task_type: str, context: str = None) -> str:
        """Основной цикл: генерирует → проверяет → при провале переделывает."""
        if not self.should_check(task_type):
            return generate_fn("")

        best_answer = None
        best_score = 0
        last_issues = []

        for attempt in range(self.max_retries + 1):
            if attempt == 0:
                answer = generate_fn("")
            else:
                feedback = (
                    f"Твой предыдущий ответ был забракован критиком.\n"
                    f"Проблемы: {last_issues}\n"
                    f"Предыдущий ответ:\n{best_answer}\n\n"
                    f"Пожалуйста, перепиши, устранив эти проблемы."
                )
                answer = generate_fn(feedback)

            # Выбираем метод проверки
            if task_type == "rag" and context:
                verdict = self.check_factual(context, answer)
            else:
                verdict = self.check_general(task, answer, task_type)

            score = verdict.get("score", 0)
            print(f"  [Критик] Попытка {attempt+1}: score={score}, verdict={verdict.get('verdict')}")

            if score > best_score:
                best_score = score
                best_answer = answer

            if verdict.get("verdict") == "accept" and score >= self.min_score:
                return answer

            last_issues = verdict.get("issues") or verdict.get("unverified_claims") or ["не указаны"]

        print(f"  [Критик] Лимит попыток исчерпан. Возвращаю лучший вариант (score={best_score}).")
        return f"[ВНИМАНИЕ: критик не подтвердил качество, лучший score={best_score}. Замечания: {last_issues}]\n\n{best_answer}"
