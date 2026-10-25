from duckduckgo_search import DDGS

def search_web(query: str, max_results: int = 3) -> str:
    """Ищет информацию в интернете."""
    try:
        results = DDGS().text(query, max_results=max_results)
        if not results:
            return "Ничего не найдено в интернете."

        output = ""
        for r in results:
            output += f"Источник: {r['title']}\nСсылка: {r['href']}\nТекст: {r['body']}\n\n"
        return output
    except Exception as e:
        return f"Ошибка поиска: {e}"
