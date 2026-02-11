import requests
import os

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

MAX_PRICE = 1.0   # временно поставим 1$, чтобы протестировать
GPU_NAME = "A100"  # временно ставим A100 для проверки

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text})

def check_vast():
    url = "https://console.vast.ai/api/v0/bundles"

    r = requests.get(url)
    data = r.json()

    if "offers" not in data:
        return

    filtered = [
        offer for offer in data["offers"]
        if GPU_NAME.lower() in offer["gpu_name"].lower()
    ]

    if not filtered:
        print("Нет GPU найдено")
        return

    cheapest = sorted(filtered, key=lambda x: x["dph_total"])[0]

    price = cheapest["dph_total"]
    gpu = cheapest["gpu_name"]
    location = cheapest["geolocation"]

    print("Найдено:", gpu, price)

    if price <= MAX_PRICE:
        send_message(
            f"🔥 Найден {gpu}\n"
            f"Цена: ${price}/час\n"
            f"Локация: {location}"
        )

if __name__ == "__main__":
    check_vast()
