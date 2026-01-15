from window_manager import WindowManager

wm = WindowManager()
title = "Trading - Google Chrome"
print(f"Testing title: '{title}'")
is_trading = wm.is_trading_platform(title)
print(f"Result: {is_trading}")

title_lower = title.lower()
keywords = ["chart", "trade", "quote", "market", "exchange"]
print(f"Keywords check: {[k for k in keywords if k in title_lower]}")
