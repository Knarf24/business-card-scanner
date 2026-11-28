# 📇 Business Card Scanner

**Live demo:** https://knarf24.github.io/business-card-scanner/

**The problem:** after a meeting, a workshop or an expo you come home with a pile of business cards. Typing each one
into your phone takes ages, so most of them end up lost in a drawer.

**The app:** snap a card with your phone (or upload a picture). The app **reads the card** and fills in the name, job
title, company, mobile, office and fax numbers, email, website and address. You check it, then:

- **Add to phone:** download a vCard (`.vcf`) that opens straight in the Contacts app on iPhone and Android
  (and imports into Outlook and Gmail).
- **Save to my list:** keep all your scanned cards, search them, edit them, and download them all as one vCard file
  or as a **CSV spreadsheet** for Excel or Google Sheets. Scanning the same person twice updates them instead of
  adding a copy.

It works with dark cards, coloured cards and phone photos of a card lying on a table. Three sample cards are built in,
so you can try it without a card. The card logic is written in **Python** and runs **inside your browser** with
[Pyodide](https://pyodide.org); the text is read by [Tesseract.js](https://tesseract.projectnaptha.com/).
**Nothing is uploaded**: pictures and contacts stay on your device. Hosted free on GitHub Pages.

Built by combining three GeeksforGeeks Python projects:

| GeeksforGeeks project | What it does here |
|---|---|
| [Visiting Card Scanner GUI](https://www.geeksforgeeks.org/python/visiting-card-scanner-gui-application-using-python/) | Reads the text on the card with Tesseract OCR (Tesseract.js in the browser, `pytesseract` in `desktop.py`) |
| [Text Detection and Extraction using OpenCV and OCR](https://www.geeksforgeeks.org/python/text-detection-and-extraction-using-opencv-and-ocr/) | Cleans the photo before reading: best-contrast grey, dark cards flipped, shadows evened out, card cut out of the background (NumPy) |
| [Email Id Extractor](https://www.geeksforgeeks.org/python/email-id-extractor-project-from-sites-in-scrapy-python/) | Pulls out emails with patterns, and the same idea for phone numbers and websites |

## How it works

1. **Clean up the photo** (`card.clean_image`): keeps the colour channel with the most contrast, turns light-on-dark
   cards around, divides by the paper brightness to remove shadows and glare, stretches the contrast, and cuts the card
   out of the table around it.
2. **Read the text:** Tesseract finds the text blocks and reads each line, with its size and how sure it is.
3. **Find the details** (`card.parse_lines`):
   - emails, websites and phone numbers by pattern, fixing common OCR slips (`site-com`, a dropped first letter);
   - phones sorted into mobile / office / fax from labels ("Cell", "M:", "Tel", "Fax") or the number itself;
   - address lines from street words, post codes and place names;
   - job title and company from keyword lists (Manager, Founder, Accountant… / Ltd, (Pty), Studio, Partners…),
     or the company from the email's domain;
   - the name from the "First Last" lines, preferring the one that matches the email and is printed biggest.
4. **Save:** `card.to_vcard` writes vCard 3.0 (with "van der Merwe" style surnames kept together) and `card.to_csv`
   writes a spreadsheet that is safe to open in Excel.

## Files

| File | What it is |
|---|---|
| `card.py` | All the logic (Python): photo clean-up, finding the details, vCard and CSV, duplicate check |
| `web/` | The page: `index.html`, `main.js` (camera/upload, Tesseract.js, form, saved list), `style.css`, sample cards, Pyodide in `web/pyodide/`, Tesseract.js in `web/tesseract/` |
| `desktop.py` | The same scanner on your computer: `python desktop.py card1.jpg card2.jpg` writes `contacts.vcf` and `contacts.csv` |
| `tests/test_card.py` | Offline tests: `python tests/test_card.py` |
| `tools/make_samples.py` | Draws the sample cards (made-up people and companies) |
| `build_site.sh`, `.github/workflows/pages.yml` | Builds `_site/` and publishes it to GitHub Pages |

## Tips

Take the photo straight on, in good light, with the card filling most of the picture. If the card is sideways, press
**Turn**. English-language cards read best. Always give the details a quick check before saving.

## Fast loading

The page shows straight away and Python starts in the background, so nothing waits on a
"Starting Python" screen. Anything that needs Python simply waits for it if you are quicker.

- **Saved on the device** (`web/sw.js`): after the first visit, Python (Pyodide) and its packages are kept in
  the browser, so a refresh or a later visit doesn't download them again. Every app on the same site shares
  that one saved copy. The app's own files are still fetched fresh, so updates show up right away.
- **Quick restart** (`web/pyfast.js`): the first visit also saves a snapshot of a freshly started Python.
  Later visits restore it instead of starting Python from scratch (about 1.2 s down to 0.3 s on a laptop).
  If the snapshot can't be used (for example after a Pyodide upgrade), Python starts normally and a new one
  is saved.
- `build_site.sh` writes the Pyodide version into `sw.js`, so upgrading `web/pyodide/` needs no other change.


## License

MIT. Pyodide is MPL-2.0, Tesseract.js and Tesseract are Apache-2.0. The people and companies on the sample cards are
made up.
