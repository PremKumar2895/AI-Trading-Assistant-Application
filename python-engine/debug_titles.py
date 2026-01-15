import pygetwindow as gw

print("--- Visible Windows ---")
try:
    titles = gw.getAllTitles()
    for t in titles:
        if t.strip():
            print(f"[{t}]")
except Exception as e:
    print(f"Error: {e}")
print("-----------------------")
