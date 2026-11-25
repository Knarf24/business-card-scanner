"""Business Card Scanner on your computer.

    python desktop.py card1.jpg card2.png ...        # prints each contact, writes contacts.vcf and contacts.csv
    python desktop.py --out mycards cards/*.jpg      # writes mycards.vcf and mycards.csv

Needs: pip install -r requirements.txt, plus the Tesseract program
(Windows: https://github.com/UB-Mannheim/tesseract/wiki, macOS: brew install tesseract, Linux: apt install tesseract-ocr).
"""
import argparse
import sys

import numpy as np
from PIL import Image

import card


def read_card(path, clean=True):
    import pytesseract

    im = Image.open(path).convert("RGBA")
    scale = min(2.5, 1600 / max(im.size))
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    if clean:
        data, w, h = card.clean_image(im.tobytes(), im.width, im.height)
        pic = Image.frombytes("L", (w, h), data)
    else:
        pic = im.convert("RGB")
    d = pytesseract.image_to_data(pic, config="--psm 3", output_type=pytesseract.Output.DICT)
    lines = {}
    for i, word in enumerate(d["text"]):
        if not word.strip():
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        ln = lines.setdefault(key, {"words": [], "top": 10 ** 9, "bottom": 0, "conf": []})
        ln["words"].append(word)
        ln["top"] = min(ln["top"], d["top"][i])
        ln["bottom"] = max(ln["bottom"], d["top"][i] + d["height"][i])
        ln["conf"].append(float(d["conf"][i]))
    out = [{"text": " ".join(l["words"]), "height": l["bottom"] - l["top"], "conf": float(np.mean(l["conf"]))}
           for l in lines.values()]
    return card.parse_lines(out)


def main():
    ap = argparse.ArgumentParser(description="Read business cards into contacts (vCard + CSV).")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out", default="contacts", help="name for the .vcf and .csv files")
    ap.add_argument("--no-clean", action="store_true", help="skip the photo clean-up")
    a = ap.parse_args()
    contacts = []
    for path in a.images:
        c = read_card(path, clean=not a.no_clean)
        print(f"\n{path}")
        for k in card.FIELDS:
            if c[k]:
                print(f"  {card.LABELS[k]:13} {c[k]}")
        if card.find_duplicate(c, contacts) >= 0:
            print("  (already in the list, skipped)")
            continue
        contacts.append(c)
    if not contacts:
        sys.exit("No contacts found.")
    with open(a.out + ".vcf", "w", encoding="utf-8", newline="") as f:
        f.write(card.to_vcards(contacts))
    with open(a.out + ".csv", "w", encoding="utf-8-sig", newline="") as f:
        f.write(card.to_csv(contacts))
    print(f"\nSaved {len(contacts)} contact(s) to {a.out}.vcf and {a.out}.csv")


if __name__ == "__main__":
    main()
