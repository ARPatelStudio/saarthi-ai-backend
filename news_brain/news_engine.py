import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

def get_latest_news(topic: str):
    """
    DuckDuckGo Search ka use karke taaza khabrein fetch karta hai bina kisi API key ke.
    """
    try:
        # max_results 3 rakha hai taaki response fast ho aur LLM overload na ho
        results = DDGS().news(keywords=topic, max_results=3)
        
        if not results:
            return f"Boss, mujhe '{topic}' par koi taaza khabar nahi mili."
        
        news_text = f"Here is the latest news for '{topic}':\n"
        for i, r in enumerate(results, 1):
            title = r.get('title', 'Unknown Title')
            source = r.get('source', 'Unknown Source')
            news_text += f"{i}. {title} (Source: {source})\n"
            
        return news_text
        
    except Exception as e:
        logger.error(f"News Search Error: {e}")
        return "Boss, duniya ki khabrein lane mein thoda server error aa raha hai."
