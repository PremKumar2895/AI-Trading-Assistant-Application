import pygetwindow as gw
import time

print("--- Start Window Dump ---")
try:
    titles = gw.getAllTitles()
    for t in titles:
        if t.strip():
            print(f"'{t}'")
except Exception as e:
    print(f"Error: {e}")
print("--- End Window Dump ---")
