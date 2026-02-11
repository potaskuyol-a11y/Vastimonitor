import requests
import os
import json

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

MAX_PRICE = 0.50  # твой реальный предел
MIN_VRAM = 40960  # 40 GB в MB

STATE_FILE = "state.json"

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text})

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def check_vast():
    url = "https://console.vast.ai/api/v0/bundles"
    r = requests.get(url)
    data = r.json()

    if "offers" not in data:
        return

    # фильтр ≥ 40GB VRAM
    valid = [
        o for o in data["offers"]
        if o["gpu_total_ram"] >= MIN_VRAM
    ]

    if not valid:
        return

    cheapest = sorted(valid, key=lambda x: x["dph_total"])[0]

    price = cheapest["dph_total"]
    gpu = cheapest["gpu_name"]
    location = cheapest["geolocation"]
    vram = cheapest["gpu_total_ram"] // 1024

    state = load_state()
    last_price = state.get("last_price")

    # отправляем только если новая цена лучше прошлой
    if price <= MAX_PRICE and (last_price is None or price < last_price):

        send_message(
            f"🔥 Новый лучший вариант\n"
            f"GPU: {gpu}\n"
            f"VRAM: {vram} GB\n"
            f"Цена: ${round(price,4)}/час\n"
            f"Локация: {location}"
        )

        state["last_price"] = price
        save_state(state)

if __name__ == "__main__":
    check_vast()
