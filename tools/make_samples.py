"""Draws the sample business cards in web/samples/ (made-up people and companies).

    python tools/make_samples.py

Needs Pillow and the DejaVu / Liberation fonts (any TrueType fonts work; change FONT_DIR).
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join(os.path.dirname(__file__), "..", "web", "samples")
F = "/usr/share/fonts/truetype/"


def font(name, size):
    for p in (F + "liberation/" + name, F + "dejavu/" + name):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


W, H = 1050, 600


def card_classic():
    im = Image.new("RGB", (W, H), "#fbfaf6")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 22, H], fill="#1f6f5c")
    d.ellipse([850, 50, 960, 160], fill="#1f6f5c")
    d.text((905, 105), "UB", font=font("LiberationSans-Bold.ttf", 46), fill="white", anchor="mm")
    d.text((70, 60), "Ubuntu Build Solutions (Pty) Ltd", font=font("LiberationSans-Bold.ttf", 30), fill="#1f6f5c")
    d.text((70, 170), "Thandi Nkosi", font=font("LiberationSans-Bold.ttf", 62), fill="#222")
    d.text((72, 248), "Senior Project Manager", font=font("LiberationSans-Regular.ttf", 32), fill="#555")
    r = font("LiberationSans-Regular.ttf", 28)
    y = 340
    for line in ["M: +27 82 555 0142", "T: +27 11 555 0190", "thandi.nkosi@ubuntubuild.example.com",
                 "14 Jacaranda Street, Rosebank", "Johannesburg 2196, South Africa"]:
        d.text((72, y), line, font=r, fill="#333")
        y += 46
    return im


def card_dark():
    im = Image.new("RGB", (W, H), "#17181c")
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - 16, W, H], fill="#e8a33d")
    d.text((W - 70, 70), "KORA STUDIO", font=font("LiberationSans-Bold.ttf", 34), fill="#e8a33d", anchor="ra")
    d.text((70, 150), "JAMES OKAFOR", font=font("LiberationSans-Bold.ttf", 60), fill="#f2f2f2")
    d.text((72, 228), "Founder & Lead Designer", font=font("LiberationSans-Regular.ttf", 32), fill="#c9c9c9")
    r = font("LiberationSans-Regular.ttf", 29)
    y = 330
    for line in ["+234 803 555 0177", "hello@korastudio.example.org", "www.korastudio.example.org",
                 "22 Admiralty Way, Lekki Phase 1", "Lagos, Nigeria"]:
        d.text((72, y), line, font=r, fill="#ececec")
        y += 46
    return im


def card_colour():
    im = Image.new("RGB", (W, H), "#d9ecf7")
    d = ImageDraw.Draw(im)
    d.polygon([(W, 0), (W, 260), (760, 0)], fill="#2b6cb0")
    d.text((70, 55), "Fynbos Accounting Partners", font=font("DejaVuSerif-Bold.ttf", 34), fill="#1d4e80")
    d.text((70, 150), "Lerato van der Merwe", font=font("DejaVuSerif-Bold.ttf", 52), fill="#12355b")
    d.text((72, 222), "Chartered Accountant (SA)", font=font("DejaVuSerif.ttf", 30), fill="#2b6cb0")
    r = font("DejaVuSans.ttf", 26)
    left = ["Tel  021 555 0134", "Cell 072 555 0189", "Fax  021 555 0135"]
    right = ["lerato@fynbosaccounting.example.net", "Suite 5, 2nd Floor, Wale Street", "Cape Town 8001"]
    y = 330
    for a in left:
        d.text((72, y), a, font=r, fill="#12355b")
        y += 44
    y = 470
    for b in right:
        d.text((72, y), b, font=r, fill="#12355b")
        y += 40
    return im


def as_photo(card, seed=3):
    """Put the card on a table, slightly turned, with uneven light, like a phone photo."""
    random.seed(seed)
    bw, bh = 1400, 1000
    bg = Image.new("RGB", (bw, bh), "#8a6a4a")
    px = bg.load()
    for y in range(bh):
        for x in range(0, bw):
            g = int(14 * math.sin(y / 9.0 + math.sin(x / 140.0) * 3))
            px[x, y] = (138 + g, 106 + g, 74 + g)
    shadow = Image.new("L", (W + 60, H + 60), 0)
    ImageDraw.Draw(shadow).rectangle([30, 30, W + 30, H + 30], fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18)).rotate(4, expand=True)
    c = card.convert("RGBA").rotate(4, expand=True, resample=Image.BICUBIC)
    ox, oy = (bw - c.width) // 2, (bh - c.height) // 2
    bg.paste((0, 0, 0), (ox + 14, oy + 18), shadow.crop((0, 0, c.width, c.height)))
    bg.paste(c, (ox, oy), c)
    # uneven light: brighter top-left, darker bottom-right
    import numpy as np
    yy, xx = np.mgrid[0:bh, 0:bw]
    shade = 1.0 - 0.45 * ((xx / bw + yy / bh) / 2.0)
    bg = Image.fromarray((np.asarray(bg, dtype=np.float32) * shade[:, :, None]).clip(0, 255).astype(np.uint8))
    noise = Image.effect_noise((bw, bh), 10).convert("RGB")
    bg = Image.blend(bg, noise, 0.04)
    return bg.filter(ImageFilter.GaussianBlur(0.6))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    card_classic().save(os.path.join(OUT, "card-classic.png"), optimize=True)
    card_dark().save(os.path.join(OUT, "card-dark.png"), optimize=True)
    as_photo(card_colour()).save(os.path.join(OUT, "card-photo.jpg"), quality=85)
    print("written to", os.path.abspath(OUT))
