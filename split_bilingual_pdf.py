"""
Split a Belgian bilingual parliamentary PDF (NL/FR parallel-column format)
into two monolingual PDFs.

Handles two layout modes that can both occur within the SAME document:
  1. Two-column parallel pages (NL left, FR right) -> split at the detected gutter.
  2. Full-width single-language pages (e.g. annex tables) -> route the whole
     page to the correct output file based on detected language.

Usage:
    python split_bilingual_pdf.py input.pdf output_nl.pdf output_fr.pdf
"""

import sys
import fitz  # PyMuPDF
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0  # deterministic langdetect results

GUTTER_CENTER_TOLERANCE = 0.12   # gutter line must fall within +/-12% of page center
MIN_RULE_LENGTH_RATIO = 0.55     # the divider line must span at least 55% of page height


def find_gutter(page):
    """
    Two-column pages in this template have an actual printed vertical rule
    spanning almost the full body height, centered on the page. Table/annex
    pages don't have this (their vertical lines are short table-cell borders).
    This is a far more reliable signal than text-block gaps, which can
    coincidentally line up near the center of a multi-column table.
    Returns the gutter x-coordinate, or None if this isn't a two-column page.
    """
    w, h = page.rect.width, page.rect.height
    best = None
    for d in page.get_drawings():
        r = d["rect"]
        is_vertical = abs(r.x1 - r.x0) < 1.0
        length = r.y1 - r.y0
        if not is_vertical or length < MIN_RULE_LENGTH_RATIO * h:
            continue
        x = (r.x0 + r.x1) / 2
        if abs(x - w / 2) > GUTTER_CENTER_TOLERANCE * w:
            continue
        if best is None or length > best[1]:
            best = (x, length)
    return best[0] if best else None


def detect_page_language(page, fallback):
    """Detect language of a full single-column page; fall back to last known."""
    text = page.get_text().strip()
    if len(text) < 20:
        return fallback
    try:
        lang = detect(text)
    except Exception:
        return fallback
    if lang == "fr":
        return "fr"
    if lang in ("nl", "af"):  # 'af' (Afrikaans) sometimes confused with Dutch
        return "nl"
    return fallback


def split_pdf(input_path, output_nl_path, output_fr_path, log=print):
    src = fitz.open(input_path)
    out_nl = fitz.open()
    out_fr = fitz.open()

    last_single_lang = "nl"  # reasonable default for the very first page
    report = []

    for i, page in enumerate(src):
        w, h = page.rect.width, page.rect.height
        gutter = find_gutter(page)

        if gutter is not None:
            # Two-column page -> copy left half to NL, right half to FR
            left_clip = fitz.Rect(0, 0, gutter, h)
            right_clip = fitz.Rect(gutter, 0, w, h)

            p_nl = out_nl.new_page(width=w, height=h)
            p_nl.show_pdf_page(p_nl.rect, src, i, clip=left_clip)

            p_fr = out_fr.new_page(width=w, height=h)
            p_fr.show_pdf_page(p_fr.rect, src, i, clip=right_clip)

            report.append((i + 1, "two-column", f"gutter={gutter:.1f}"))
        else:
            # Single-column page -> detect language, route whole page
            lang = detect_page_language(page, last_single_lang)
            last_single_lang = lang
            target = out_nl if lang == "nl" else out_fr
            p = target.new_page(width=w, height=h)
            p.show_pdf_page(p.rect, src, i)
            report.append((i + 1, "single-column", lang))

    out_nl.save(output_nl_path)
    out_fr.save(output_fr_path)
    out_nl.close()
    out_fr.close()
    src.close()

    return report


if __name__ == "__main__":
    in_pdf, nl_out, fr_out = sys.argv[1], sys.argv[2], sys.argv[3]
    rep = split_pdf(in_pdf, nl_out, fr_out)
    for r in rep:
        print(r)
