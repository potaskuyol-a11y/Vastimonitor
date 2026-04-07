import requests
import os
import json

TG_TOKEN = os.getenv("TG_TOKEN")
CHAT_ID = os.getenv("TG_CHAT")

# --- Gonka-совместимые фильтры ---
MAX_PRICE_PER_GPU = 2.50       # макс. цена за 1 GPU, $/час
MIN_VRAM_MB = 81920            # 80 GB в MB (H100=80GB, H200=141GB)
MIN_GPUS = 8                   # минимум 8 GPU в одной машине
REQUIRED_GPUS = {"H100", "H200", "H100_SXM", "H100_SXM5", "H100_PCIE", "H200_SXM"}
MIN_CUDA = 12.6                # минимальная версия CUDA

STATE_FILE = "state.json"

def send_message(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"})

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
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

    valid = []
    for o in data["offers"]:
        gpu_name = o.get("gpu_name", "")
        num_gpus = o.get("num_gpus", 1)
        vram = o.get("gpu_total_ram", 0)
        cuda = o.get("cuda_max_good", 0)
        price_total = o.get("dph_total", 999)

        # нормализуем имя GPU для сравнения
        gpu_norm = gpu_name.replace(" ", "_").replace("-", "_")

        if gpu_norm not in REQUIRED_GPUS:
            continue
        if num_gpus < MIN_GPUS:
            continue
        if vram < MIN_VRAM_MB:
            continue
        if cuda < MIN_CUDA:
            continue

        price_per_gpu = price_total / num_gpus
        if price_per_gpu > MAX_PRICE_PER_GPU:
            continue

        valid.append(o)

    if not valid:
        return

    cheapest = sorted(valid, key=lambda x: x["dph_total"])[0]

    price_total = cheapest["dph_total"]
    num_gpus = cheapest.get("num_gpus", 1)
    price_per_gpu = price_total / num_gpus
    gpu = cheapest["gpu_name"]
    location = cheapest.get("geolocation", "N/A")
    vram = cheapest["gpu_total_ram"] // 1024
    cuda = cheapest.get("cuda_max_good", "?")
    reliability = cheapest.get("reliability", 0)
    inet_down = cheapest.get("inet_down", 0)
    offer_id = cheapest.get("id", "?")

    state = load_state()
    last_price = state.get("last_price")

    if last_price is None or price_total < last_price:
        daily_cost = round(price_total * 24, 2)

        send_message(
            f"<b>Gonka-совместимый вариант</b>\n"
            f"GPU: {num_gpus}x {gpu}\n"
            f"VRAM: {vram} GB\n"
            f"CUDA: {cuda}\n"
            f"Цена: ${round(price_total, 4)}/час (${round(price_per_gpu, 4)}/GPU)\n"
            f"В день: ${daily_cost}\n"
            f"Reliability: {round(reliability * 100, 1)}%\n"
            f"Download: {round(inet_down, 1)} Mbps\n"
            f"Локация: {location}\n"
            f"Offer ID: {offer_id}"
        )

        state["last_price"] = price_total
        save_state(state)

if __name__ == "__main__":
    check_vast()
