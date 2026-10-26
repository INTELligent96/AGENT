import json
from llm.registry import LLMRegistry


class Critic:
    def __init__(self, registry, config):
        self.registry = registry
        cfg = config.get('self_check', {})
        self.enabled = cfg.get('enabled', True)
        self.force_always = cfg.get('force_always', False)
        self.max_retries = cfg.get('max_retries', 2)
        self.min_score = cfg.get('min_score', 7)
        self.critic_model_key = cfg.get('critic_model', 'local_logic')
        self.default_critic_key = cfg.get('default_model_for_check', 'local_fast')

    def should_check(self, task_type):
        if not self.enabled:
            return False
        if self.force_always:
            return True
        return task_type in ['rag', 'summarize', 'translate', 'structure']

    def check_factual(self, context, answer):
        prompt = (
            'Ты - фактчекер. Проверь, все ли КОНКРЕТНЫЕ факты (имена, числа, даты, названия) в ответе '
            'подтверждаются контекстом.\n\n'
            'КОНТЕКСТ:\n' + context[:6000] + '\n\n'
            'ОТВЕТ:\n' + answer + '\n\n'
            'Верни ТОЛЬКО JSON без markdown:\n'
            '{"score": 1-10, "unverified_claims": [], "verdict": "accept" или "retry"}\n\n'
            'Правила:\n'
            '- Если в ответе есть конкретное имя/число/факт, и оно есть в контексте — accept, score 9-10.\n'
            '- Если в ответе сказано "не найдено", а в контексте факт ЕСТЬ — retry, score 3-4.\n'
            '- Если в ответе есть выдуманные факты (которых нет в контексте) — retry, score 4-5.\n'
            '- Если ответ просто пересказывает контекст без искажений — accept, score 9.'
        )
        raw = self.registry.generate_with_fallback(self.critic_model_key, prompt)
        return self._parse(raw)

    def check_general(self, task, answer, task_type):
        model_key = self.critic_model_key if task_type == 'rag' else self.default_critic_key
        prompt = (
            'Ты - критик. Оцени, отвечает ли ответ на задачу.\n\n'
            'ЗАДАЧА: ' + task + '\n'
            'ОТВЕТ: ' + answer + '\n\n'
            'Верни ТОЛЬКО JSON без markdown:\n'
            '{"score": 1-10, "issues": [], "verdict": "accept" или "retry"}\n\n'
            'Правила (ВАЖНО - будь объективным):\n'
            '- Если ответ содержит конкретный ответ на вопрос (имя, число, факт) — accept, score 8-10.\n'
            '- Если ответ - "не найдено", но вопрос простой — retry, score 3-4.\n'
            '- Если ответ размытый или уклончивый — retry, score 5-6.\n'
            '- НЕ придирайся к стилю, длине или оформлению.'
        )
        raw = self.registry.generate_with_fallback(model_key, prompt)
        return self._parse(raw)

    def _parse(self, raw):
        try:
            clean = raw.replace('```json', '').replace('```', '').strip()
            data = json.loads(clean)
            data.setdefault('score', 5)
            data.setdefault('verdict', 'retry')
            data.setdefault('issues', [])
            return data
        except Exception:
            return {'score': 7, 'issues': ['Критик не дал валидный JSON, считаем OK'], 'verdict': 'accept'}

    def run_with_retry(self, generate_fn, task, task_type, context=None):
        if not self.should_check(task_type):
            return generate_fn('')
        best_answer = None
        best_score = 0
        last_issues = []
        for attempt in range(self.max_retries + 1):
            if attempt == 0:
                answer = generate_fn('')
            else:
                fb = (
                    'Твой предыдущий ответ забракован.\n'
                    'Замечания: ' + str(last_issues) + '\n'
                    'Предыдущий ответ:\n' + str(best_answer) + '\n\n'
                    'Перепиши, устранив проблемы.'
                )
                answer = generate_fn(fb)
            if task_type == 'rag' and context:
                verdict = self.check_factual(context, answer)
            else:
                verdict = self.check_general(task, answer, task_type)
            score = verdict.get('score', 0)
            print('  [Критик] Попытка ' + str(attempt + 1) + ': score=' + str(score) + ', verdict=' + str(verdict.get('verdict')))
            if score > best_score:
                best_score = score
                best_answer = answer
            if verdict.get('verdict') == 'accept' and score >= self.min_score:
                return answer
            last_issues = verdict.get('issues') or verdict.get('unverified_claims') or ['не указаны']
        # Мягкий финал: если score >= 6, возвращаем без ругани
        if best_score >= 6:
            return best_answer
        print('  [Критик] Лимит. Лучший score=' + str(best_score))
        return '[Критик: качество ниже нормы, score=' + str(best_score) + ', замечания: ' + str(last_issues) + ']\n\n' + str(best_answer)
