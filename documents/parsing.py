"""Text extraction for PDF and Markdown files.

Returns a list of "blocks": {"text": str, "page_number": int, "heading": str}
so downstream chunking can retain page numbers (PDF) or the nearest heading
(Markdown) as citation metadata.
"""
import re

import markdown as md_lib
from markdown.extensions.toc import TocExtension


def extract_pdf_blocks(file_path: str):
    import fitz  # PyMuPDF

    blocks = []
    with fitz.open(file_path) as doc:
        page_count = doc.page_count
        for page_index in range(page_count):
            page = doc.load_page(page_index)
            text = page.get_text("text").strip()
            if text:
                blocks.append(
                    {"text": text, "page_number": page_index + 1, "heading": ""}
                )
    return blocks, page_count


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def extract_markdown_blocks(file_path: str):
    """Splits a markdown file into sections by heading, so each chunk can be
    tagged with the heading it falls under. 'page_number' is set to a
    synthetic, monotonically increasing section number since markdown has
    no native pages."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    matches = list(_HEADING_RE.finditer(raw))
    blocks = []

    if not matches:
        text = raw.strip()
        if text:
            blocks.append({"text": text, "page_number": 1, "heading": ""})
        return blocks, max(1, len(blocks))

    # Anything before the first heading
    if matches[0].start() > 0:
        preamble = raw[: matches[0].start()].strip()
        if preamble:
            blocks.append({"text": preamble, "page_number": 1, "heading": ""})

    for i, m in enumerate(matches):
        heading_text = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        section_text = raw[start:end].strip()
        section_number = i + (2 if blocks and blocks[0]["heading"] == "" else 1)
        full_text = f"{heading_text}\n{section_text}" if section_text else heading_text
        blocks.append(
            {"text": full_text, "page_number": i + 1, "heading": heading_text}
        )

    return blocks, len(blocks)


def extract_blocks(file_path: str, file_type: str):
    if file_type == "pdf":
        return extract_pdf_blocks(file_path)
    if file_type == "md":
        return extract_markdown_blocks(file_path)
    raise ValueError(f"Unsupported file type: {file_type}")
