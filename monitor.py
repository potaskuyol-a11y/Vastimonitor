import requests
import os

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

MAX_PRICE = 100   # предел $/час
GPU_NAME = "RTX_3090"

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text})

def check_vast():
    url = "https://console.vast.ai/api/v0/bundles"
    params = {
        "q": f"gpu_name={GPU_NAME}",
        "order": "dph_total"
    }

    r = requests.get(url, params=params)
    data = r.json()

    if "offers" not in data or len(data["offers"]) == 0:
        return

    cheapest = sorted(data["offers"], key=lambda x: x["dph_total"])[0]
    price = cheapest["dph_total"]

    if price <= MAX_PRICE:
        send_message(f"🔥 Дёшево! {GPU_NAME} за ${price}/час")

if __name__ == "__main__":
    check_vast()
