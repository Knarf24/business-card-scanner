"""Business Card Scanner: the Python brain.

Turns the text read from a business card into a tidy contact, and saves contacts as
vCard (.vcf, for phones and email apps) or CSV (for Excel and Google Sheets).

It also cleans up the card photo before the text is read (grey, contrast, dark cards
turned light, uneven light evened out) using NumPy.

Runs the same way in the browser (Pyodide) and on a computer (desktop.py).
No network access: everything stays on the device.
"""

import csv
import io
import json
import re

FIELDS = ["name", "title", "company", "mobile", "phone", "fax", "email", "website", "address", "notes"]

LABELS = {
    "name": "Name", "title": "Job title", "company": "Company", "mobile": "Mobile",
    "phone": "Office phone", "fax": "Fax", "email": "Email", "website": "Website",
    "address": "Address", "notes": "Notes",
}

# ---------------------------------------------------------------- image clean-up

def clean_image(rgba, width, height):
    """Clean a card photo for reading. rgba: bytes (width*height*4).
    Returns (grey bytes, new width, new height): the card cut out from what is around it.

    1. Grey: keep the colour channel with the most contrast (coloured text on coloured
       cards often vanishes in plain grey).
    2. Dark card with light text: turn it around, so text is always dark on light.
    3. Even out the light: divide by a blurred copy (removes shadows and glare).
    4. Stretch the contrast.
    5. Cut the card out of the background.
    """
    import numpy as np

    if hasattr(rgba, "to_bytes"):  # a browser image (JsProxy) from Pyodide
        rgba = rgba.to_bytes()
    img = np.frombuffer(bytes(rgba), dtype=np.uint8).reshape(height, width, 4)[:, :, :3].astype(np.float32)
    lum = img @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    best, best_spread = lum, _spread(lum)
    for c in range(3):
        s = _spread(img[:, :, c])
        if s > best_spread * 1.25:
            best, best_spread = img[:, :, c], s
    grey = best

    # Background is the most common brightness; if it is darker than the text, flip.
    # Look at the middle of the picture (where the card is) so a dark table doesn't count.
    mid = grey[height // 5: height - height // 5, width // 5: width - width // 5]
    if np.median(mid) < 110:
        grey = 255.0 - grey

    # Even out the light (a big blur is the background; text is small detail on top).
    bg = _background(grey, max(16, min(width, height) // 10))
    flat = np.clip(grey / np.maximum(bg, 1.0) * 255.0, 0, 255)

    lo, hi = np.percentile(flat, [1, 99])
    if hi - lo < 10:
        hi = lo + 10
    out = np.clip((flat - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    x0, y0, x1, y1 = _card_box(out)
    out = np.ascontiguousarray(out[y0:y1, x0:x1])
    return out.tobytes(), x1 - x0, y1 - y0


def _longest_run(mask):
    best, start, run_start = (0, len(mask)), None, None
    best_len = 0
    for i, m in enumerate(list(mask) + [False]):
        if m and run_start is None:
            run_start = i
        elif not m and run_start is not None:
            if i - run_start > best_len:
                best_len, best = i - run_start, (run_start, i)
            run_start = None
    return best, best_len


def _card_box(out):
    """Cut away the table around the card: the card is the big light area (text is small and dark)."""
    import numpy as np
    h, w = out.shape
    light = out > 170
    (y0, y1), ny = _longest_run(light.mean(1) > 0.45)
    if ny < h * 0.25:
        return 0, 0, w, h
    (x0, x1), nx = _longest_run(light[y0:y1].mean(0) > 0.45)
    if nx < w * 0.25:
        return 0, 0, w, h
    py, px = int(h * 0.04), int(w * 0.04)
    return max(0, x0 - px), max(0, y0 - py), min(w, x1 + px), min(h, y1 + py)


def _background(grey, b):
    """Paper brightness everywhere: the brightest pixels in each b x b block (text is darker), smoothed."""
    import numpy as np
    h, w = grey.shape
    gh, gw = -(-h // b), -(-w // b)
    p = np.pad(grey, ((0, gh * b - h), (0, gw * b - w)), mode="edge")
    blocks = p.reshape(gh, b, gw, b).transpose(0, 2, 1, 3).reshape(gh, gw, b * b)
    small = np.percentile(blocks, 95, axis=2).astype(np.float32)
    small = _box_blur(small, 3)
    big = np.repeat(np.repeat(small, b, axis=0), b, axis=1)[:h, :w]
    return _box_blur(big, b | 1)


def _spread(a):
    import numpy as np
    lo, hi = np.percentile(a, [5, 95])
    return float(hi - lo)


def _box_blur(a, k):
    """Mean over a k x k square, using running sums (fast, no SciPy needed)."""
    import numpy as np
    r = k // 2
    p = np.pad(a, r, mode="edge").astype(np.float64)
    h, w = a.shape
    s = np.zeros((p.shape[0] + 1, p.shape[1] + 1))
    s[1:, 1:] = p.cumsum(0).cumsum(1)
    tot = s[k:k + h, k:k + w] - s[0:h, k:k + w] - s[k:k + h, 0:w] + s[0:h, 0:w]
    return (tot / (k * k)).astype(np.float32)


# ---------------------------------------------------------------- reading the text

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+\s?@\s?[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
WEB_RE = re.compile(r"\b((?:https?://)?(?:www\.)?[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.(?:com|org|net|io|co|biz|info|africa|dev|app|tech|me|us|uk|za|ke|ng|gh|zw|in|au|ca|de|fr)(?:\.[a-z]{2})?(?:/[^\s]*)?)\b", re.I)
PHONE_RE = re.compile(r"(?:\+|\(?\b0)[\d\s().\-/]{7,}\d|\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b")

MOBILE_WORDS = ("mobile", "mob", "cell", "cel", "m:", "m.", "c:", "whatsapp", "handy")
FAX_WORDS = ("fax", "f:", "f.")
PHONE_WORDS = ("tel", "phone", "office", "t:", "t.", "o:", "p:", "direct", "landline", "work")

TITLE_WORDS = {
    "manager", "director", "engineer", "ceo", "cto", "cfo", "coo", "founder", "co-founder", "officer",
    "consultant", "designer", "developer", "sales", "head", "lead", "specialist", "accountant", "attorney",
    "partner", "president", "owner", "analyst", "agent", "advisor", "adviser", "architect", "assistant",
    "coordinator", "executive", "representative", "chef", "doctor", "dr", "nurse", "teacher", "lecturer",
    "professor", "photographer", "broker", "realtor", "estate", "marketing", "chief", "supervisor",
    "administrator", "technician", "planner", "strategist", "editor", "writer", "producer", "lawyer",
    "pharmacist", "therapist", "secretary", "treasurer", "chairman", "chairperson", "principal", "vp",
    "vice", "senior", "junior", "associate", "intern", "trainer", "coach", "stylist", "mechanic",
    "electrician", "plumber", "builder", "contractor", "dentist", "surgeon", "bookkeeper", "recruiter",
}
COMPANY_WORDS = {
    "ltd", "pty", "(pty)", "inc", "inc.", "llc", "llp", "plc", "gmbh", "group", "solutions", "studio",
    "studios", "company", "co.", "corp", "corporation", "holdings", "bank", "consulting", "technologies",
    "technology", "tech", "labs", "partners", "associates", "agency", "enterprises", "services",
    "industries", "foundation", "trust", "media", "design", "logistics", "systems", "ventures", "capital",
    "clinic", "hospital", "school", "academy", "university", "college", "restaurant", "cafe", "hotel",
    "motors", "construction", "properties", "realty", "insurance", "network", "digital", "software",
    "trading", "supplies", "investments", "attorneys", "accountants", "pharmacy", "foods", "farms",
}
ADDRESS_WORDS = {
    "street", "st", "st.", "road", "rd", "rd.", "avenue", "ave", "ave.", "drive", "dr.", "lane", "ln",
    "boulevard", "blvd", "way", "close", "crescent", "place", "pl", "suite", "floor", "unit", "building",
    "bldg", "po", "p.o.", "box", "park", "centre", "center", "square", "court", "highway", "hwy",
    "plaza", "estate", "office", "tower", "house", "complex", "industrial",
}
PLACE_WORDS = {
    "johannesburg", "cape", "town", "durban", "pretoria", "gqeberha", "bloemfontein", "polokwane",
    "harare", "bulawayo", "nairobi", "lagos", "accra", "kampala", "gaborone", "windhoek", "lusaka",
    "london", "new", "york", "sandton", "soweto", "midrand", "centurion", "stellenbosch",
    "south", "africa", "kenya", "nigeria", "ghana", "zimbabwe", "botswana", "namibia", "zambia",
    "usa", "uk", "gauteng", "kwazulu-natal", "kzn", "western", "eastern",
}


def _words(s):
    return [w.strip(",.:;|()").lower() for w in s.split()]


def _clean_line(s):
    s = s.replace("|", " ").replace("—", "-").replace("–", "-").replace("’", "'")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip(" -•·*_~=")


def _digits(s):
    return re.sub(r"\D", "", s)


def _tidy_phone(raw):
    raw = raw.strip()
    plus = raw.startswith("+")
    d = _digits(raw)
    if len(d) < 7 or len(d) > 15:
        return ""
    # Keep the spacing the card used, just tidy it.
    t = re.sub(r"[^\d+()\s\-]", " ", raw)
    t = re.sub(r"\s+", " ", t).strip()
    return ("+" if plus and not t.startswith("+") else "") + t


def _phone_kind(text_before, line):
    ctx = (text_before[-14:] if text_before else "").lower()
    for words, kind in ((FAX_WORDS, "fax"), (MOBILE_WORDS, "mobile"), (PHONE_WORDS, "phone")):
        for w in words:
            if w in ctx:
                return kind
    low = line.lower()
    for words, kind in ((FAX_WORDS, "fax"), (MOBILE_WORDS, "mobile")):
        if any(re.search(r"(^|\W)" + re.escape(w.rstrip(":.")) + r"\b", low) for w in words):
            return kind
    return ""


def _looks_like_name(s):
    ws = s.split()
    if not 2 <= len(ws) <= 4 or any(ch.isdigit() for ch in s) or "@" in s:
        return False
    if any(w in TITLE_WORDS or w in COMPANY_WORDS or w in ADDRESS_WORDS for w in _words(s)):
        return False
    letters = [w for w in ws if re.match(r"^[A-Za-zÀ-ÿ'\-.]+$", w)]
    if len(letters) != len(ws):
        return False
    caps = sum(1 for w in ws if w[0].isupper() or w.lower() in ("van", "de", "der", "du", "le", "la", "von"))
    return caps >= len(ws) - 1


def parse_lines(lines):
    """lines: list of {"text": str, "height": number (optional), "conf": number (optional)}.
    Returns a contact dict with every field in FIELDS (empty string when not found)."""
    c = {k: "" for k in FIELDS}
    items = []
    for ln in lines:
        if isinstance(ln, str):
            ln = {"text": ln}
        raw = ln.get("text", "")
        conf = float(ln.get("conf") if ln.get("conf") is not None else 100)
        # Unsure lines are usually logos or patterns, unless they hold an email or a number.
        if conf < 35 and "@" not in raw and len(_digits(raw)) < 7:
            continue
        # OCR slips in emails: "name@site-com", "name @ site.com"
        raw = re.sub(r"(@[\w.\-]+)[-,](com|net|org|co|io|biz|info)\b", r"\1.\2", raw)
        # "Name | Title" or "Tel • Email" on one line: treat each part as its own line.
        for part in re.split(r"\s*[|•·]\s*|\s{3,}", raw):
            t = _clean_line(part)
            if len(t) >= 2:
                items.append({"text": t, "height": float(ln.get("height") or 0), "conf": float(ln.get("conf") or 100)})
    left = []
    phones = []
    extra_emails, extra_webs = [], []

    for it in items:
        t = it["text"]
        rest = t
        # email
        for m in EMAIL_RE.finditer(t):
            e = m.group(0).replace(" ", "").strip(".")
            if not c["email"]:
                c["email"] = e
            elif e != c["email"]:
                extra_emails.append(e)
            rest = rest.replace(m.group(0), " ")
        # phones
        pos = 0
        for m in PHONE_RE.finditer(rest):
            num = _tidy_phone(m.group(0))
            if num:
                phones.append((_phone_kind(rest[pos:m.start()], t), num))
                pos = m.end()
        rest = PHONE_RE.sub(" ", rest)
        # website
        for m in WEB_RE.finditer(rest):
            w = m.group(1).strip(".,/")
            if "." in w and not re.fullmatch(r"[\d.]+", w):
                if not c["website"]:
                    c["website"] = w
                elif w.lower() != c["website"].lower():
                    extra_webs.append(w)
                rest = rest.replace(m.group(0), " ")
        rest = re.sub(r"\b(?:tel|phone|mobile|mob|cell|fax|email|e-mail|web|website|www|office|direct|whatsapp|[tmfecwop])\s*[:.]\s*", " ", rest, flags=re.I)
        rest = _clean_line(re.sub(r"\s+", " ", rest))
        if len(re.sub(r"[^A-Za-z0-9]", "", rest)) >= 2:
            left.append({**it, "text": rest})

    # Sort phones into mobile / office / fax.
    unsorted = []
    for kind, num in phones:
        if kind and not c[kind]:
            c[kind] = num
        elif kind != "fax":
            unsorted.append(num)
    for num in unsorted:
        if num in (c["mobile"], c["phone"], c["fax"]):
            continue
        d = _digits(num)
        mobile_like = bool(re.match(r"^(?:27[678]|0[678]|2547|07|234[789]|0[789]0|2637|447|07)", d))
        if mobile_like and not c["mobile"]:
            c["mobile"] = num
        elif not c["phone"]:
            c["phone"] = num
        elif not c["mobile"]:
            c["mobile"] = num

    # Address: lines with street words or a post code, plus the town/country lines.
    addr = []
    for it in left:
        ws = _words(it["text"])
        has_street = any(w in ADDRESS_WORDS for w in ws) and any(ch.isdigit() for ch in it["text"])
        has_place = sum(w in PLACE_WORDS for w in ws) >= 1 and (any(ch.isdigit() for ch in it["text"]) or len(ws) <= 4)
        has_code = bool(re.search(r"\b\d{4,6}\b", it["text"])) and len(ws) <= 6
        if has_street or (addr and (has_place or has_code)) or (has_place and has_code):
            addr.append(it)
    for it in addr:
        if it in left:
            left.remove(it)
    if addr:
        c["address"] = ", ".join(a["text"].strip(", ") for a in addr)

    # Job title and company by keywords.
    for it in list(left):
        ws = _words(it["text"])
        if not c["title"] and any(w in TITLE_WORDS for w in ws) and len(ws) <= 8:
            c["title"] = it["text"]
            left.remove(it)
    for it in list(left):
        ws = _words(it["text"])
        if not c["company"] and any(w in COMPANY_WORDS for w in ws) and not _looks_like_name(it["text"]):
            c["company"] = it["text"]
            left.remove(it)

    # Name: a "First Last" line; prefer one matching the email, then the biggest text.
    local = re.split(r"@", c["email"])[0].lower() if c["email"] else ""
    local_parts = [p for p in re.split(r"[._\-+0-9]", local) if len(p) >= 2]

    def name_score(it):
        s = 0.0
        ws = _words(it["text"])
        if any(p in w or w in p for p in local_parts for w in ws if len(w) >= 2):
            s += 50
        s += it["height"]
        return s

    names = [it for it in left if _looks_like_name(it["text"])]
    if names:
        best = max(names, key=name_score)
        c["name"] = _title_case(best["text"])
        left.remove(best)

    # OCR often drops the first letter of a line: "erato@..." when the name is "Lerato".
    if c["email"] and c["name"]:
        user, _, host = c["email"].partition("@")
        for w in c["name"].lower().split():
            if len(w) >= 4 and user.lower().startswith(w[1:]) and not user.lower().startswith(w):
                c["email"] = w[0] + user + "@" + host
                break

    # Company from the email or web domain, if no line said it.
    domain = ""
    if c["email"]:
        domain = c["email"].split("@")[-1]
    elif c["website"]:
        domain = re.sub(r"^(https?://)?(www\.)?", "", c["website"], flags=re.I)
    dom_word = re.split(r"[./]", domain)[0].lower() if domain else ""
    if not c["company"] and left:
        if dom_word and dom_word not in ("gmail", "yahoo", "outlook", "hotmail", "icloud", "live", "mweb", "telkomsa", "webmail"):
            for it in left:
                squashed = re.sub(r"[^a-z]", "", it["text"].lower())
                if squashed and (squashed in dom_word or dom_word in squashed or squashed[:5] == dom_word[:5]):
                    c["company"] = it["text"]
                    left.remove(it)
                    break
    if not c["company"] and left:
        # The biggest remaining line is usually the logo / company name.
        big = max(left, key=lambda it: it["height"])
        if big["height"] and big["height"] >= max(i["height"] for i in items) * 0.8 and len(big["text"]) <= 40:
            c["company"] = big["text"]
            left.remove(big)
    label_only = re.compile(r"^(?:(?:tel|phone|mobile|mob|cell|fax|email|e-mail|web|website|office|direct|whatsapp|address)\W*)+$", re.I)
    notes = extra_emails + extra_webs + [it["text"] for it in left
                                         if len(re.sub(r"[^A-Za-z0-9]", "", it["text"])) >= 3 and not label_only.match(it["text"])]
    c["notes"] = "; ".join(notes[:6])
    return c


def _title_case(s):
    if s.isupper() or s.islower():
        parts = []
        for w in s.split():
            lw = w.lower()
            parts.append(lw if lw in ("van", "de", "der", "du", "von") else "-".join(p[:1].upper() + p[1:] for p in lw.split("-")))
        return " ".join(parts)
    return s


def parse_text(text):
    """Plain text version (one line per card line)."""
    return parse_lines([{"text": t} for t in text.splitlines()])


# ---------------------------------------------------------------- saving contacts

def _vesc(s):
    return (s or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _split_name(name):
    ws = (name or "").split()
    if not ws:
        return "", ""
    if len(ws) == 1:
        return "", ws[0]
    # Keep "van der Merwe" style surnames together.
    i = len(ws) - 1
    while i > 1 and ws[i - 1].lower() in ("van", "de", "der", "du", "le", "la", "von", "da", "dos"):
        i -= 1
    return " ".join(ws[i:]), " ".join(ws[:i])


def _fold(line):
    """vCard lines should be at most 75 bytes; longer ones continue on the next line after a space."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 75:
            out.append(cur)
            cur = " " + ch
        else:
            cur += ch
    out.append(cur)
    return "\r\n".join(out)


def to_vcard(contact):
    c = {k: (contact.get(k) or "").strip() for k in FIELDS}
    last, first = _split_name(c["name"])
    lines = ["BEGIN:VCARD", "VERSION:3.0",
             f"N:{_vesc(last)};{_vesc(first)};;;",
             f"FN:{_vesc(c['name'] or c['company'] or c['email'] or 'Unknown')}"]
    if c["company"]:
        lines.append(f"ORG:{_vesc(c['company'])}")
    if c["title"]:
        lines.append(f"TITLE:{_vesc(c['title'])}")
    if c["mobile"]:
        lines.append(f"TEL;TYPE=CELL,VOICE:{c['mobile']}")
    if c["phone"]:
        lines.append(f"TEL;TYPE=WORK,VOICE:{c['phone']}")
    if c["fax"]:
        lines.append(f"TEL;TYPE=WORK,FAX:{c['fax']}")
    if c["email"]:
        lines.append(f"EMAIL;TYPE=INTERNET,WORK:{c['email']}")
    if c["website"]:
        url = c["website"] if re.match(r"https?://", c["website"], re.I) else "https://" + c["website"]
        lines.append(f"URL:{url}")
    if c["address"]:
        lines.append(f"ADR;TYPE=WORK:;;{_vesc(c['address'])};;;;")
    if c["notes"]:
        lines.append(f"NOTE:{_vesc(c['notes'])}")
    lines.append("END:VCARD")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def to_vcards(contacts):
    return "".join(to_vcard(c) for c in contacts)


def to_csv(contacts):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([LABELS[k] for k in FIELDS] + ["Scanned"])
    for c in contacts:
        row = []
        for k in FIELDS + ["scanned"]:
            v = str(c.get(k) or "")
            if v[:1] in ("=", "+", "-", "@") and k not in ("mobile", "phone", "fax"):
                v = "'" + v  # stop spreadsheets treating it as a formula
            row.append(v)
        w.writerow(row)
    return buf.getvalue()


def find_duplicate(contact, contacts):
    """Index of a saved contact that is the same person (same email or same phone), else -1."""
    e = (contact.get("email") or "").lower()
    nums = {_digits(contact.get(k) or "")[-9:] for k in ("mobile", "phone")} - {""}
    for i, o in enumerate(contacts):
        if e and e == (o.get("email") or "").lower():
            return i
        other = {_digits(o.get(k) or "")[-9:] for k in ("mobile", "phone")} - {""}
        if nums & other:
            return i
    return -1


# ---------------------------------------------------------------- browser helpers (JSON in, JSON/text out)

def parse_json(lines_json):
    return json.dumps(parse_lines(json.loads(lines_json)))


def vcards_json(contacts_json):
    return to_vcards(json.loads(contacts_json))


def csv_json(contacts_json):
    return to_csv(json.loads(contacts_json))


def duplicate_json(contact_json, contacts_json):
    return find_duplicate(json.loads(contact_json), json.loads(contacts_json))


def fields_json():
    return json.dumps([{"key": k, "label": LABELS[k]} for k in FIELDS])
