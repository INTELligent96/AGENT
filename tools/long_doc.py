import os
from pathlib import Path
from llm.registry import LLMRegistry
from documents.extractors import extract_text
from core.prompts import SUMMARIZE_PROMPT

class LongDocumentProcessor:
    def __init__(self, agent_config: dict, tools_config: dict, registry: LLMRegistry, output_dir="output"):
        self.config = agent_config
        self.tools = tools_config
        self.registry = registry
        self.output_dir = Path(output_dir) / "checkpoints"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        rag_cfg = self.config.get("rag", {})
        self.chunk_size = rag_cfg.get("chunk_size", 3000) # Для резюме берем куски побольше

    def process(self, file_path: str) -> str:
        """Читает большой файл, режет на куски и делает резюме с сохранением чекпоинтов."""
        file_path = Path(file_path)
        print(f"\n[LongDoc] Начинаю обработку файла: {file_path.name}")

        text = extract_text(str(file_path), self.tools)
        if text.startswith("[Ошибка]"):
            return text

        # Создаем папку для чекпоинтов конкретно этого файла
        doc_dir = self.output_dir / file_path.stem
        doc_dir.mkdir(parents=True, exist_ok=True)

        # Простой сплиттер по предложениям, чтобы не рвать мысли
        chunks = []
        current_chunk = ""
        for sentence in text.replace('\n', ' ').split('. '):
            if len(current_chunk) + len(sentence) > self.chunk_size:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk += sentence + ". "
        if current_chunk:
            chunks.append(current_chunk)

        print(f"[LongDoc] Файл разбит на {len(chunks)} частей.")

        summaries = []
        for i, chunk in enumerate(chunks):
            checkpoint_file = doc_dir / f"part_{i}.txt"

            # Если чекпоинт уже есть (прервались в прошлый раз), читаем с диска!
            if checkpoint_file.exists():
                print(f"[LongDoc] Часть {i+1}/{len(chunks)} уже обработана. Загружаю с диска.")
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    summaries.append(f.read())
                continue

            print(f"[LongDoc] Резюмирую часть {i+1}/{len(chunks)}...")
            prompt = SUMMARIZE_PROMPT.format(text=chunk)
            summary = self.registry.generate_with_fallback("default_model", prompt)

            # Сохраняем чекпоинт
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                f.write(summary)
            summaries.append(summary)

        # Финальное резюме (склеиваем куски)
        print("[LongDoc] Генерация финального резюме...")
        final_text = "\n\n".join(summaries)
        final_prompt = SUMMARIZE_PROMPT.format(text=final_text)
        final_summary = self.registry.generate_with_fallback("default_model", final_prompt)

        # Сохраняем итог
        final_file = self.output_dir / f"FINAL_{file_path.stem}.txt"
        with open(final_file, "w", encoding="utf-8") as f:
            f.write(final_summary)

        return f"Готово! Итоговое резюме сохранено в {final_file}"
