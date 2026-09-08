import yfinance as yf
import logging

logger = logging.getLogger(__name__)

def get_stock_price(symbol: str):
    """Fetches live stock data using yfinance (Free)"""
    try:
        # Indian stocks usually end with .NS (NSE) or .BO (BSE)
        if symbol.isalpha() and not symbol.endswith('.NS') and not symbol.endswith('.BO'):
            symbol = symbol.upper() + ".NS"

        ticker = yf.Ticker(symbol)
        data = ticker.history(period="1d")
        if data.empty:
            return f"Boss, mujhe '{symbol}' ka live data nahi mila. Symbol check kar lijiye."

        current_price = data['Close'].iloc[-1]
        prev_close = ticker.info.get('previousClose', current_price)
        change = current_price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0

        trend = "up 📈" if change > 0 else "down 📉"
        return f"Boss, {symbol.upper()} ka current price ₹{current_price:,.2f} chal raha hai. Aaj yeh {abs(change_pct):.2f}% {trend} hai."
    except Exception as e:
        logger.error(f"Stock API Error: {e}")
        return "Boss, stock market ka data fetch karne mein issue aa raha hai."
