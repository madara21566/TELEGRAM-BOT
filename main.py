import time
import requests

# Apna website URL yaha dal
URL = "https://telegram-bot-z3zl.onrender.com"

def keep_alive():
    while True:
        try:
            response = requests.get(URL)
            print(f"[PING] {time.strftime('%Y-%m-%d %H:%M:%S')} - {response.status_code}")
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(1200)  # 20 minutes (20*60 = 1200 sec)

if __name__ == "__main__":
    keep_alive()
    
