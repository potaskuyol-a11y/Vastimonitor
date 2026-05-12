"""Parse mail_data/emails.jsonl and write a deduplicated contacts.xlsx.

Columns: Имя | Компания | Должность | Телефон | Email
Contacts are merged by email address; the first non-empty value wins for the
other fields, with signature fields attributed to the sender of the message
they appeared in.

Usage:
    python extract_contacts.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from openpyxl import Workbook

EMAILS_FILE = Path("mail_data/emails.jsonl")
OUTPUT_FILE = Path("mail_data/contacts.xlsx")

EMAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}")
ADDR_RE = re.compile(r'(?:"?([^"<>@]+?)"?\s*)?<?([\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,})>?')
PHONE_RE = re.compile(
    r"(?:\+?\d[\s\-().]?){10,14}\d"
)

POSITION_KEYWORDS = {
    "директор", "менеджер", "руководитель", "специалист", "инженер",
    "разработчик", "аналитик", "консультант", "администратор", "президент",
    "генеральный", "заместитель", "начальник", "главный", "старший",
    "ведущий", "эксперт", "координатор", "управляющий", "архитектор",
    "тимлид", "продакт", "проджект", "бухгалтер", "юрист", "ассистент",
    "помощник", "секретарь", "маркетолог", "дизайнер",
    "ceo", "cto", "cfo", "coo", "cio", "manager", "director", "engineer",
    "developer", "lead", "head", "chief", "officer", "consultant",
    "specialist", "product", "project", "team lead", "owner", "founder",
}

COMPANY_MARKERS = ("ООО", "ОАО", "ЗАО", "ПАО", "АО ", '"АО"', "ИП ", "LLC", "Ltd",
                   "Inc", "GmbH", "Corp", "Group", "Холдинг", "холдинг")

GREETING_RE = re.compile(
    r"^(с\s+уважением|с\s+ув\.?|best\s+regards|kind\s+regards|regards|sincerely|thanks|thank you|br)[\s,.\-—]*$",
    re.IGNORECASE,
)


def parse_address(s: str | None) -> tuple[str, str] | None:
    if not s:
        return None
    m = ADDR_RE.search(s)
    if not m:
        return None
    name = (m.group(1) or "").strip().strip('"\'')
    email = m.group(2).strip().lower()
    if "@" not in email:
        return None
    return name, email


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if not (11 <= len(digits) <= 13):
        return None
    if digits.startswith("7") and len(digits) == 11:
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return "+" + digits


def extract_phones(text: str) -> list[str]:
    if not text:
        return []
    seen: list[str] = []
    for m in PHONE_RE.findall(text):
        norm = normalize_phone(m)
        if norm and norm not in seen:
            seen.append(norm)
    return seen


def parse_signature(body: str) -> dict:
    if not body:
        return {}
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    tail = lines[-30:]
    block = "\n".join(tail)

    result: dict = {"name": None, "company": None, "position": None, "phone": None}

    phones = extract_phones(block)
    if phones:
        result["phone"] = phones[0]

    for line in tail:
        low = line.lower()
        if any(kw in low for kw in POSITION_KEYWORDS) and 3 <= len(line) <= 110:
            result["position"] = line
            break

    for line in tail:
        if any(mk in line for mk in COMPANY_MARKERS) and len(line) <= 140:
            result["company"] = line
            break

    for i, line in enumerate(tail):
        if GREETING_RE.match(line):
            for j in range(i + 1, min(i + 4, len(tail))):
                cand = tail[j]
                if 2 <= len(cand.split()) <= 5 and len(cand) <= 60 and not EMAIL_RE.search(cand):
                    result["name"] = cand
                    break
            break

    return result


def better(a: str, b: str) -> str:
    if not a:
        return b
    if not b:
        return a
    return b if len(b) > len(a) else a


def main() -> int:
    if not EMAILS_FILE.exists():
        print(f"Error: {EMAILS_FILE} not found. Run scrape_mailru.py first.")
        return 1

    contacts: dict[str, dict] = {}

    with EMAILS_FILE.open(encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            body = rec.get("body") or ""
            sender = parse_address(rec.get("fromBlock") or "")
            sig = parse_signature(body)

            sources: list[tuple[str, str]] = []
            if sender:
                sources.append(sender)
            for r in rec.get("recipients") or []:
                parsed = parse_address(r)
                if parsed:
                    sources.append(parsed)
            for tt in rec.get("tooltips") or []:
                parsed = parse_address(tt)
                if parsed:
                    sources.append(parsed)
            for found in EMAIL_RE.findall(body):
                sources.append(("", found.lower()))

            for name, email in sources:
                if not email or "@" not in email:
                    continue
                c = contacts.setdefault(
                    email,
                    {"name": "", "company": "", "position": "", "phone": "", "email": email},
                )
                if name:
                    c["name"] = better(c["name"], name)
                if sender and sender[1] == email:
                    if sig.get("name"):
                        c["name"] = better(c["name"], sig["name"])
                    if sig.get("company") and not c["company"]:
                        c["company"] = sig["company"]
                    if sig.get("position") and not c["position"]:
                        c["position"] = sig["position"]
                    if sig.get("phone") and not c["phone"]:
                        c["phone"] = sig["phone"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"
    ws.append(["Имя", "Компания", "Должность", "Телефон", "Email"])
    for c in sorted(contacts.values(), key=lambda x: x["email"]):
        ws.append([c["name"], c["company"], c["position"], c["phone"], c["email"]])

    for col, width in zip("ABCDE", (30, 35, 35, 24, 38)):
        ws.column_dimensions[col].width = width

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    wb.save(OUTPUT_FILE)
    print(f"Saved {len(contacts)} unique contacts to {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
