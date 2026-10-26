from pathlib import Path
from .indexer import RAGIndexer
from llm.registry import LLMRegistry


PRONOUNS = [
    'он', 'она', 'оно', 'они', 'это', 'этот', 'эта', 'эти',
    'там', 'тут', 'его', 'её', 'их', 'ему', 'ей', 'тот', 'та', 'те',
    'той', 'того', 'этого', 'этой', 'который', 'которая', 'которое', 'которые',
]

GENERIC_WORDS = [
    'что в папке', 'что находится в папке', 'расскажи о папке', 'расскажи про папку',
    'про папку', 'о папке', 'обзор папки', 'перечень файлов', 'список файлов',
    'содержимое папки', 'покажи файлы', 'какие файлы',
]


class RAGQuestionAnswerer:
    def __init__(self, config, tools_config, registry):
        self.indexer = RAGIndexer(config, tools_config)
        self.registry = registry

    def _clean_text(self, text):
        parts = []
        for w in text.split():
            # Windows-путь: D:/foo или C:/foo
            if len(w) >= 3 and w[1] == ':' and not w[2].isalnum():
                continue
            if w.startswith('/') and len(w) > 2:
                continue
            parts.append(w)
        text = ' '.join(parts)
        lower = text.lower()
        for gw in GENERIC_WORDS:
            lower = lower.replace(gw, ' ')
        return ' '.join(lower.split()).strip()

    def _build_search_query(self, question, history):
        if not history:
            return question
        last_user = None
        for h in reversed(history):
            if h.get('role') == 'user':
                c = h.get('content', '')
                if c.startswith('Контекст:') or c.startswith('[Диалог]'):
                    continue
                last_user = c
                break
        if not last_user:
            return question
        is_short = len(question) < 60
        words = question.lower().split()
        has_pronoun = any(p in words for p in PRONOUNS)
        if is_short or has_pronoun:
            clean_prev = self._clean_text(last_user)
            clean_curr = self._clean_text(question)
            combined = (clean_prev + ' ' + clean_curr).strip()
            if not combined:
                combined = question
            print('  [RAG] Поиск с контекстом: ' + combined[:120])
            return combined
        return question

    def _get_source_filter(self, folder):
        if not folder:
            return None
        try:
            files = [str(f) for f in Path(folder).rglob('*') if f.is_file()]
            if not files:
                return None
            return {'source': {'$in': files}}
        except Exception:
            return None

    def ask(self, question, history=None, last_folder=None, folder_filter=None):
        search_query = self._build_search_query(question, history)
        print("Поиск по базе: '" + search_query[:80] + "'...")
        where = self._get_source_filter(folder_filter)
        context_chunks = self.indexer.search(search_query, top_k=12, where=where)
        if not context_chunks:
            return 'В базе данных не найдено информации по этому вопросу.'
        print('  [RAG] Источники:')
        for c in context_chunks:
            print('    - ' + Path(c['source']).name + ' (part ' + str(c['chunk_id']) + ')')
        context_text = ''
        for i, chunk in enumerate(context_chunks, 1):
            src = Path(chunk['source']).name
            context_text += '--- Фрагмент ' + str(i) + ' (' + src + ', part ' + str(chunk['chunk_id']) + ') ---\n'
            context_text += chunk['text'] + '\n\n'
        system_prompt = 'Ты - ассистент по документам. Отвечай ТОЛЬКО на основе фрагментов. Прочитай ВСЕ фрагменты. Если ответ есть хотя бы в одном - выведи его. Указывай файл-источник.'
        user_prompt = ''
        if history:
            user_prompt += 'ИСТОРИЯ:\n'
            for h in history[-6:]:
                role = 'Пользователь' if h['role'] == 'user' else 'Ассистент'
                user_prompt += role + ': ' + str(h['content'])[:300] + '\n'
            user_prompt += '\n'
        if last_folder:
            user_prompt += 'КОНТЕКСТ_ПАПКИ: ' + last_folder + '\n\n'
        user_prompt += 'КОНТЕКСТ:\n' + context_text + '\n\nВОПРОС: ' + question
        print('Генерация ответа...')
        return self.registry.generate_with_fallback('complex_reasoning', user_prompt, system_prompt)

