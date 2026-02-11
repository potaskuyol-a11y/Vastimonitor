import requests
import os

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text})

def check_vast():
    url = "https://console.vast.ai/api/v0/bundles"

    try:
        r = requests.get(url)

        print("STATUS CODE:", r.status_code)
        print("HEADERS:", r.headers)
        print("RESPONSE START:")
        print(r.text[:1500])  # первые 1500 символов

    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    check_vast()
