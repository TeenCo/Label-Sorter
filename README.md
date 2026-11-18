# Shipping Label Sorter (eBay + TikTok Shop + InPost)

Windows desktop tool that scans downloaded shipping-label PDFs, classifies **every page (and every label on
multi-label pages)** as eBay, TikTok or InPost, and writes up to four PDFs using native PDF operations only:

| File | Contents |
|---|---|
| `YYYY-MM-DD_EBAY.pdf` | every eBay label, in download order (only created if there is one) |
| `YYYY-MM-DD_TIKTOK.pdf` | every TikTok label, in download order (only created if there is one) |
| `YYYY-MM-DD_INPOST.pdf` | every InPost label, in download order (only created if there is one) |
| `YYYY-MM-DD_PRINTS.pdf` | **all** original pages, unmodified, original order and sizes |

Plus `YYYY-MM-DD_REPORT.txt` and `YYYY-MM-DD_EXCEPTIONS.csv` listing every flagged page with its
**PRINTS PDF page number**. Existing outputs are never overwritten (`_2`, `_3` ... is added to all files instead).

## 1. Install (Windows)

1. Install **Python 3.12** from python.org (tick *Add python.exe to PATH*).
2. In this folder open a terminal and run:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Optional - OCR fallback (Tesseract).** Only used for labels with no readable platform text (scans,
   logos drawn as pictures). Windows build: <https://github.com/UB-Mannheim/tesseract/wiki>. The app finds it
   automatically; otherwise set `TESSERACT_CMD` to the full path of `tesseract.exe`.

## 2. Run

```
python main.py
```

The window has a dark sidebar with five steps. Steps unlock as you progress and finished steps get a tick.

1. **Files** - drop PDFs on the window (or click / `Ctrl+O`). Sorted by download time, oldest first; fix the order
   with *Move up/down* (`Alt+Up/Down`), *Sort by name*, *Remove* (`Del`). Pick the output folder.
2. **Analysis** - live view: the page being read, running counters per platform, and a feed of results.
   When a label is **ambiguous or unreadable the analysis pauses on this screen** and asks:
   **eBay (E) / TikTok (T) / InPost (I) / Skip (S) / Decide later (L)**. The preview shows the exact label and can
   switch to the full page. Platforms named on the label are marked. No popup, no terminal.
3. **Results** - every label in one table. Filter chips (All / eBay / TikTok / InPost / Needs decision / Skipped),
   click a row to preview it, move rows with the buttons or keys `E T I S` (multi-select works).
4. **Exceptions** - flagged pages (non-standard size, duplicates, multi-label pages...) with preview, CSV export.
   **Generate** stays disabled while any label is undecided - the app never guesses.
5. **Output** - progress, then the generated files, then an optional single confirmation to delete the originals
   (only after the outputs were reopened and verified; failed files are never offered).

## 3. How labels are recognised

1. Native PDF text, case-insensitive: `eBay`, `TikTok` (also `Tik Tok`), `InPost` (one word, not part of another word).
   Two or more platform names on one label = ambiguous -> the app asks you.
2. No platform text: OCR of that label region (needs Tesseract).
3. Otherwise: the app asks you.

Patterns live in `core/platforms/<platform>.py` - add a spelling there and nothing else needs to change.
InPost labels bought through eBay are recognised by the InPost branding; if such a label also contains the word
"eBay", it is treated as ambiguous and you pick InPost once.

Page sizes: 4x6 in (+/-6 pt), A4, other (e.g. A6 InPost labels are kept at their own size and flagged as
non-standard, which is informational only). Pages larger than ~1.6 labels are searched for several labels; a
split is accepted only if every part looks like a complete label, otherwise the page is kept whole and flagged.

## 4. Integrity notes

* Pages are copied with PyMuPDF `insert_pdf`; nothing is rasterized, resized or recompressed. Previews on screen
  are rendered separately and never used for output.
* Labels on a multi-label page are separated by setting the page's **CropBox**; the rest of the page still exists
  invisibly inside each cropped page. Do not share those files if neighbouring addresses matter.
* Rotated pages, or pages that already have a smaller CropBox, are never cropped automatically - flagged instead.
* Duplicate labels are flagged but never removed.
* Outputs are written as `*.part`, reopened with PyMuPDF **and** pypdf, size-checked, and only then renamed.
  On any failure nothing is left behind and no original is deleted.

## 5. Project layout

```
main.py                 entry point
core/                   engine - no GUI code, fully testable
  config.py models.py   thresholds, data classes (Platform enum incl. InPost)
  platforms/            one module per platform: ebay.py tiktok.py inpost.py (+ registry in __init__)
  classifier.py         text + OCR classification
  label_detector.py     sizes + multi-label detection
  pdf_analyzer.py       scan pages; AnalysisHooks (progress, live preview, ask_platform)
  pdf_processor.py      output generation + reports      file_manager.py  naming, ordering, deletion
  validation.py         verification of generated PDFs   rendering.py     on-screen page previews
ui/                     PySide6 interface
  theme.py              palette + stylesheet             widgets.py   shared widgets
  sidebar.py            step navigation                  workers.py   background threads + pause/ask bridge
  main_window.py        batch state + navigation         dialogs.py
  pages/                files_page analysis_page results_page exceptions_page output_page
tests/                  engine tests (no GUI needed)
```
Log file: `%LOCALAPPDATA%\ShippingLabelSorter\label_sorter.log`.

## 6. Tests

```
pip install -r requirements-dev.txt
python -m unittest discover -s tests -t . -v        (or: pytest)
```

## 7. Build an .exe

```
build_exe.bat
```
Builds a windowed `--onedir` app (no console needed). Tesseract is not bundled.
