"""Offline tests for card.py:  python tests/test_card.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import card  # noqa: E402

CLASSIC = [
    {"text": "Ubuntu Build Solutions (Pty) Ltd", "height": 22},
    {"text": "Thandi Nkosi", "height": 45},
    {"text": "Senior Project Manager", "height": 23},
    {"text": "M: +27 82 555 0142", "height": 20},
    {"text": "T: +27 11 555 0190", "height": 20},
    {"text": "thandi.nkosi@ubuntubuild.example.com", "height": 20},
    {"text": "14 Jacaranda Street, Rosebank", "height": 20},
    {"text": "Johannesburg 2196, South Africa", "height": 20},
]

DARK = """KORA STUDIO
JAMES OKAFOR
Founder & Lead Designer
+234 803 555 0177
hello@korastudio.example.org
www.korastudio.example.org
22 Admiralty Way, Lekki Phase 1
Lagos, Nigeria"""

COLOUR = """Fynbos Accounting Partners
Lerato van der Merwe
Chartered Accountant (SA)
Tel 021 555 0134
Cell 072 555 0189
Fax 021 555 0135
lerato@fynbosaccounting.example.net
Suite 5, 2nd Floor, Wale Street
Cape Town 8001"""

ONE_LINE = """Sipho Dlamini | Electrician
Sparks & Co. Electrical Services
Cell: 083 555 0101  Email: sipho@sparks.example.com"""


def check(got, want):
    bad = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
    assert not bad, f"wrong fields: {bad}\nfull result: {got}"


def test_classic():
    check(card.parse_lines(CLASSIC), {
        "name": "Thandi Nkosi", "title": "Senior Project Manager",
        "company": "Ubuntu Build Solutions (Pty) Ltd", "mobile": "+27 82 555 0142", "phone": "+27 11 555 0190",
        "email": "thandi.nkosi@ubuntubuild.example.com",
        "address": "14 Jacaranda Street, Rosebank, Johannesburg 2196, South Africa"})


def test_dark_caps():
    check(card.parse_text(DARK), {
        "name": "James Okafor", "title": "Founder & Lead Designer", "company": "KORA STUDIO",
        "mobile": "+234 803 555 0177", "email": "hello@korastudio.example.org",
        "website": "www.korastudio.example.org", "address": "22 Admiralty Way, Lekki Phase 1, Lagos, Nigeria"})


def test_colour():
    check(card.parse_text(COLOUR), {
        "name": "Lerato van der Merwe", "title": "Chartered Accountant (SA)", "company": "Fynbos Accounting Partners",
        "phone": "021 555 0134", "mobile": "072 555 0189", "fax": "021 555 0135",
        "address": "Suite 5, 2nd Floor, Wale Street, Cape Town 8001"})


def test_mixed_lines():
    check(card.parse_text(ONE_LINE), {
        "name": "Sipho Dlamini", "title": "Electrician", "company": "Sparks & Co. Electrical Services",
        "mobile": "083 555 0101", "email": "sipho@sparks.example.com"})


def test_ocr_slips():
    got = card.parse_lines([
        {"text": "Lerato van der  Merwe", "height": 90, "conf": 94},
        {"text": "~~ %%", "height": 40, "conf": 12},
        {"text": "erato@fynbos.example-net", "height": 40, "conf": 0},
        {"text": "Tel 021555 0134", "height": 40, "conf": 95},
    ])
    check(got, {"name": "Lerato van der Merwe", "email": "lerato@fynbos.example.net", "phone": "021555 0134", "notes": ""})


def test_vcard():
    c = card.parse_text(COLOUR)
    v = card.to_vcard(c)
    assert v.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n")
    assert "N:van der Merwe;Lerato;;;" in v
    assert "TEL;TYPE=CELL,VOICE:072 555 0189" in v
    assert "TEL;TYPE=WORK,FAX:021 555 0135" in v
    assert "ADR;TYPE=WORK:;;Suite 5\\, 2nd Floor\\, Wale Street\\, Cape Town 8001;;;;" in v.replace("\r\n ", "")
    assert all(len(l.encode()) <= 75 for l in v.split("\r\n"))
    assert v.endswith("END:VCARD\r\n")


def test_csv_and_duplicates():
    a = card.parse_text(COLOUR)
    b = card.parse_text(DARK)
    out = card.to_csv([a, b, {"name": "=HYPERLINK(1)"}])
    assert out.splitlines()[0].startswith("Name,Job title,Company,Mobile")
    assert "'=HYPERLINK(1)" in out
    assert card.find_duplicate({"mobile": "+27 72 555 0189"}, [b, a]) == 1
    assert card.find_duplicate({"email": "HELLO@korastudio.example.org"}, [a, b]) == 1
    assert card.find_duplicate({"email": "new@x.example.com"}, [a, b]) == -1


def test_clean_image_dark_card():
    import numpy as np
    w, h = 120, 60
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, :3] = 20          # dark card
    img[20:40, 30:90, :3] = 235  # light "text"
    img[:, :, 3] = 255
    data, w, h = card.clean_image(img.tobytes(), w, h)
    out = np.frombuffer(data, dtype=np.uint8).reshape(h, w)
    assert out[5, 5] > 200 and out[30, 60] < 60, (out[5, 5], out[30, 60])


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            n += 1
            print("ok", name)
    print(f"{n} tests passed")
