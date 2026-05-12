"""Scrape all emails from Inbox and Sent folders of Mail.ru webmail.

Launches a Chromium window, waits for you to log in manually, then iterates
through every message in the Inbox and Sent folders and saves the parsed
contents into mail_data/emails.jsonl. Progress is checkpointed after every
message, so the script can be interrupted and resumed.

Usage:
    pip install -r requirements.txt
    python -m playwright install chromium
    python scrape_mailru.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

OUTPUT_DIR = Path("mail_data")
EMAILS_FILE = OUTPUT_DIR / "emails.jsonl"
STATE_FILE = OUTPUT_DIR / "state.json"
USER_DATA_DIR = OUTPUT_DIR / "browser_profile"

FOLDERS: list[tuple[str, str]] = [
    ("inbox", "https://e.mail.ru/inbox/"),
    ("sent", "https://e.mail.ru/sent/"),
]

MSG_HREF_RE = re.compile(r"/(inbox|sent|drafts|spam|trash|archive)/(0:[\w\-]+)")


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"processed": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_email(record: dict) -> None:
    with EMAILS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def wait_for_login(page: Page) -> None:
    print("=" * 64)
    print("A browser window has opened. Please log in to Mail.ru.")
    print("After your Inbox is loaded, come back here and press Enter.")
    print("=" * 64)
    try:
        input()
    except EOFError:
        pass


def collect_message_ids(page: Page, folder_url: str) -> list[str]:
    page.goto(folder_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    found: list[str] = []
    seen: set[str] = set()
    stable_rounds = 0
    last_count = 0

    while True:
        hrefs: list[str] = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.getAttribute('href'))
                .filter(Boolean)
            """
        )
        for href in hrefs:
            m = MSG_HREF_RE.search(href)
            if m:
                mid = m.group(2)
                if mid not in seen:
                    seen.add(mid)
                    found.append(mid)

        if len(seen) == last_count:
            stable_rounds += 1
            if stable_rounds >= 4:
                break
        else:
            stable_rounds = 0
        last_count = len(seen)

        page.evaluate(
            """
            () => {
                const candidates = [
                    document.querySelector('[data-testid="mailbox:list"]'),
                    document.querySelector('.dataset__items'),
                    document.querySelector('.llc-list'),
                    document.querySelector('[class*="MessagesList"]'),
                    document.querySelector('[class*="messages-list"]'),
                    document.querySelector('[class*="js-letter-list"]'),
                    document.scrollingElement
                ].filter(Boolean);
                for (const el of candidates) {
                    el.scrollBy(0, (el.clientHeight || 800) * 3);
                }
                window.scrollBy(0, 1500);
            }
            """
        )
        page.wait_for_timeout(1400)
        print(f"  …collected {len(seen)} message ids so far")

    return found


def scrape_message(page: Page, folder_name: str, msg_id: str) -> dict:
    url = f"https://e.mail.ru/{folder_name}/{msg_id}/"
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(
            '[class*="letter"], [class*="message-body"], [class*="letter__body"]',
            timeout=15000,
        )
    except PWTimeout:
        pass
    page.wait_for_timeout(400)

    data: dict = page.evaluate(
        """
        () => {
            const pick = (sels) => {
                for (const s of sels) {
                    const el = document.querySelector(s);
                    if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
                }
                return null;
            };
            const pickAll = (sels) => {
                const out = [];
                for (const s of sels) {
                    document.querySelectorAll(s).forEach(el => {
                        const t = el.innerText && el.innerText.trim();
                        if (t) out.push(t);
                        const title = el.getAttribute && el.getAttribute('title');
                        if (title) out.push(title);
                    });
                }
                return out;
            };
            const subject = pick([
                'h2.letter__subject',
                '[class*="letter__subject"]',
                '[class*="subject"] h2',
                '[class*="subject"]'
            ]) || document.title;
            const fromBlock = pick([
                '.letter__author',
                '[class*="letter__author"]',
                '[class*="message-from"]',
                '[data-testid="message-from"]'
            ]);
            const date = pick([
                '.letter__date',
                '[class*="letter__date"]',
                '[class*="message-date"]',
                'time'
            ]);
            const recipients = pickAll([
                '.letter__recipients a',
                '[class*="letter__recipients"] a',
                '[class*="recipients"] a',
                '[class*="contact-name"]'
            ]);
            // Body — Mail.ru sometimes uses an iframe for HTML letters
            let body = '';
            const bodyHosts = [
                '.letter-body',
                '[class*="letter__body"]',
                '[class*="letter-body"]',
                '[class*="message-body"]'
            ];
            for (const s of bodyHosts) {
                const el = document.querySelector(s);
                if (!el) continue;
                if (el.tagName === 'IFRAME') {
                    try { body = el.contentDocument.body.innerText; } catch (e) {}
                } else {
                    body = el.innerText;
                }
                if (body) break;
            }
            if (!body) {
                const iframe = document.querySelector('iframe');
                if (iframe) {
                    try { body = iframe.contentDocument.body.innerText; } catch (e) {}
                }
            }
            // Also try to surface raw header-like contact strings present in tooltips
            const tooltips = Array.from(document.querySelectorAll('[title*="@"]'))
                .map(e => e.getAttribute('title')).filter(Boolean);
            return { subject, fromBlock, date, recipients, body, tooltips };
        }
        """
    )
    data["id"] = msg_id
    data["folder"] = folder_name
    data["url"] = url
    return data


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    state = load_state()
    processed: set[str] = set(state.get("processed", []))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30000)

        page.goto("https://e.mail.ru/login/")
        wait_for_login(page)

        try:
            for folder_name, folder_url in FOLDERS:
                print(f"\n=== Folder: {folder_name} ===")
                print("Scrolling the list to collect message ids…")
                ids = collect_message_ids(page, folder_url)
                print(f"Found {len(ids)} messages in {folder_name}.")

                for i, mid in enumerate(ids, 1):
                    key = f"{folder_name}:{mid}"
                    if key in processed:
                        continue
                    try:
                        rec = scrape_message(page, folder_name, mid)
                        append_email(rec)
                        processed.add(key)
                        if i % 20 == 0:
                            state["processed"] = list(processed)
                            save_state(state)
                        print(f"  [{i}/{len(ids)}] {folder_name} {mid} OK")
                    except Exception as e:  # noqa: BLE001
                        print(f"  [{i}/{len(ids)}] {folder_name} {mid} FAILED: {e}")
                    page.wait_for_timeout(350)

                state["processed"] = list(processed)
                save_state(state)
        finally:
            state["processed"] = list(processed)
            save_state(state)
            print(f"\nSaved messages to {EMAILS_FILE}")
            print("You can close the browser window now.")
            try:
                ctx.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
