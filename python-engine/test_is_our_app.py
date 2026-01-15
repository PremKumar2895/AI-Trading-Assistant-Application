from window_manager import WindowManager

wm = WindowManager()

test_cases = [
    "AI Trading Assistant",
    "Electron App",
    "AI-Trading-Assistant-Application - File Explorer",
    "AI-Trading-Assistant-Application - Antigravity - Walkthrough",
    "Trading - Google Chrome",
    "Binomo - Google Chrome",
    "Code - AI-Trading-Assistant-Application"
]

print("--- Testing _is_our_app Logic ---")
for title in test_cases:
    is_our = wm._is_our_app(title)
    print(f"'{title}' -> {is_our}")
