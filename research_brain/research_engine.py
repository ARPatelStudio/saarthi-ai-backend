import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

def deep_research(topic: str):
    """Executes a multi-layered deep web research and formats a comprehensive report."""
    try:
        results = DDGS().text(topic, max_results=5)
        if not results:
            return f"Boss, '{topic}' par koi solid data nahi mila."
        
        report = f"🧠 Deep Research Report: {topic.upper()}\n" + "="*40 + "\n"
        for i, r in enumerate(results, 1):
            report += f"[{i}] {r.get('title')}\nSource snippet: {r.get('body')}\n\n"
        
        report += "Conclusion: Data compiled successfully. Aap chahein toh main isey n8n ke through Cloud Vault mein save kar sakta hoon."
        return report
    except Exception as e:
        logger.error(f"R&D Brain Error: {e}")
        return "Boss, R&D module network constraint hit kar raha hai."
