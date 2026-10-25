import subprocess
import sys
import os

def validate_python_code(code: str, timeout_sec: int = 15) -> tuple[bool, str]:
    clean_code = code.replace("```python", "").replace("```", "").strip()
    test_file = "temp_validation_test.py"

    with open(test_file, "w", encoding="utf-8") as f:
        f.write(clean_code)

    try:
        # Передаем таймаут, чтобы бесконечные циклы не вешали агента
        result = subprocess.run(
            [sys.executable, test_file], 
            capture_output=True, 
            text=True, 
            timeout=timeout_sec
        )
        if result.returncode != 0:
            return False, result.stderr
        return True, "OK"
    except subprocess.TimeoutExpired:
        return False, f"Ошибка: Превышено время выполнения кода ({timeout_sec} сек). Возможно, бесконечный цикл."
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
