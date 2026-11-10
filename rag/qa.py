import re
from pathlib import Path
from .indexer import RAGIndexer
from llm.registry import LLMRegistry


PRONOUNS = ['он', 'она', 'оно', 'они', 'это', 'этот', 'эта', 'эти', 'там', 'тут', 'его', 'её', 'их', 'ему', 'ей']

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

    def _split_question(self, question):
        parts = []
        for p in re.split(r'[?;]', question):
            p = p.strip()
            if len(p) > 12:
                parts.append(p)
        return parts if len(parts) >= 2 else [question]

    def _build_search_query(self, question, history):
        if not history:
            return question
        last_user = None
        for h in reversed(history):
            if h.get('role') == 'user':
                c = h.get('content', '')
                if c.startswith('Контекст:'):
                    continue
                last_user = c
                break
        if not last_user:
            return question
        if len(question) < 60 or any(p in question.lower().split() for p in PRONOUNS):
            combined = (self._clean_text(last_user) + ' ' + self._clean_text(question)).strip()
            if combined:
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

    def _multi_search(self, question, history, where):
        subqs = self._split_question(question)
        if len(subqs) > 1:
            print('  [RAG] Multi-query: ' + str(len(subqs)) + ' подвопросов')
        seen = {}
        for i, subq in enumerate(subqs):
            sq = self._build_search_query(subq, history)
            if len(subqs) > 1:
                print('    [Подвопрос ' + str(i + 1) + '] ' + sq[:70])
            try:
                chunks = self.indexer.search(sq, top_k=8, where=where)
            except Exception as e:
                print('    [Ошибка]: ' + str(e))
                continue
            for c in chunks:
                key = (c['source'], c['chunk_id'])
                if key not in seen:
                    seen[key] = c
        return list(seen.values())[:20]

    def _format_source_line(self, i, chunk):
        meta = chunk.get('meta', {})
        src = meta.get('original_filename') or Path(chunk['source']).name
        extra = []
        if meta.get('converted_from'):
            extra.append('сконвертирован из ' + meta['converted_from'])
        if 'page' in meta:
            extra.append('стр. ' + str(meta['page']))
        if 'section' in meta:
            extra.append('раздел: «' + meta['section'] + '»')
        if 'sheet' in meta:
            extra.append('лист: «' + meta['sheet'] + '»')
        header = str(i) + '. ' + src
        if extra:
            header += ' (' + ', '.join(extra) + ')'
        header += ' [часть ' + str(chunk['chunk_id']) + ']'
        preview = chunk['text'][:120].replace('\n', ' ').strip()
        return header + ': «' + preview + '...»'

    def ask(self, question, history=None, last_folder=None, folder_filter=None):
        where = self._get_source_filter(folder_filter)
        chunks = self._multi_search(question, history, where)
        if not chunks:
            return 'В базе данных не найдено информации по этому вопросу.'
        print('  [RAG] Найдено чанков: ' + str(len(chunks)))
        print('  [RAG] Источники:')
        for c in chunks:
            meta = c.get('meta', {})
            tag = ''
            if 'page' in meta: tag = ' (стр. ' + str(meta['page']) + ')'
            elif 'section' in meta: tag = ' (раздел: ' + meta['section'][:40] + ')'
            elif 'sheet' in meta: tag = ' (лист: ' + meta['sheet'] + ')'
            print('    - ' + Path(c['source']).name + ' [часть ' + str(c['chunk_id']) + ']' + tag)

        context_text = ''
        for i, chunk in enumerate(chunks, 1):
            src = Path(chunk['source']).name
            meta = chunk.get('meta', {})
            loc = ''
            if 'page' in meta: loc = ', стр. ' + str(meta['page'])
            elif 'section' in meta: loc = ', раздел: ' + meta['section']
            elif 'sheet' in meta: loc = ', лист: ' + meta['sheet']
            context_text += '--- Фрагмент ' + str(i) + ' (' + src + ', часть ' + str(chunk['chunk_id']) + loc + ') ---\n'
            context_text += chunk['text'] + '\n\n'

        system_prompt = (
            'Ты - эксперт-аналитик. Отвечай СТРОГО по фрагментам.\n'
            'ПРАВИЛА:\n'
            '1. Каждый факт цитируй [файл, часть N].\n'
            '2. Числа (запасы, содержания, тонны) приводи ТОЧНО и ПОЛНОСТЬЮ.\n'
            '3. Методику цитируй дословно в кавычках.\n'
            '4. Исходные данные перечисляй списком.\n'
            '5. Не пиши "все фрагменты", указывай конкретные файлы и части.\n'
            '6. Если ответа нет - "в документах не найдено".'
        )

        user_prompt = ''
        if history:
            user_prompt += 'ИСТОРИЯ:\n'
            for h in history[-4:]:
                role = 'Пользователь' if h['role'] == 'user' else 'Ассистент'
                user_prompt += role + ': ' + str(h['content'])[:200] + '\n'
            user_prompt += '\n'
        if last_folder:
            user_prompt += 'КОНТЕКСТ_ПАПКИ: ' + last_folder + '\n\n'
        user_prompt += 'КОНТЕКСТ:\n' + context_text + '\n\nВОПРОС: ' + question

        print('Генерация ответа...')
        answer = self.registry.generate_with_fallback('complex_reasoning', user_prompt, system_prompt)

        sources = '\n\n' + '=' * 50 + '\nИСПОЛЬЗОВАННЫЕ ИСТОЧНИКИ:\n'
        for i, chunk in enumerate(chunks, 1):
            sources += self._format_source_line(i, chunk) + '\n'
        return answer + sources
