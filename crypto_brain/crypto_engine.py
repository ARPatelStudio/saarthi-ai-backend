import requests
import logging

logger = logging.getLogger(__name__)

def get_crypto_price(coin_name: str, currency: str = "inr"):
    """
    CoinGecko API ka use karke free live crypto prices fetch karta hai.
    """
    try:
        # CoinGecko requires lowercase coin ids (e.g., 'bitcoin', 'ethereum')
        coin_id = coin_name.lower().strip()
        curr = currency.lower().strip()
        
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies={curr}"
        res = requests.get(url, timeout=8).json()
        
        if coin_id in res:
            price = res[coin_id][curr]
            # Format price with commas (e.g., 50,00,000)
            formatted_price = "{:,.2f}".format(price)
            return f"Boss, {coin_name.capitalize()} ki current live price abhi {formatted_price} {curr.upper()} chal rahi hai."
        else:
            return f"Boss, mujhe '{coin_name}' coin ka data nahi mila. Kya naam sahi hai?"
            
    except Exception as e:
        logger.error(f"Crypto API Error: {e}")
        return "Boss, crypto market se connect karne mein thoda network glitch aa raha hai."
