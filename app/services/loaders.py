import io

from pypdf import PdfReader


def load_text(filename: str, raw: bytes) -> str:
    """Back-compat: full text joined across pages (no page info)."""
    return "\n".join(text for _, text in load_segments(filename, raw))


def load_segments(filename: str, raw: bytes) -> list[tuple[int | None, str]]:
    """Return [(page_or_None, text)] — page is 1-indexed for PDFs, None otherwise."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "pdf":
        return [(page, text) for page, text in load_pdf_pages(raw) if text.strip()]
    if suffix in ("txt", "md"):
        return [(None, load_plain(raw))]
    raise ValueError(f"unsupported file type: {filename} (use .pdf/.txt/.md)")


def load_plain(raw: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def load_pdf_pages(raw: bytes) -> list[tuple[int, str]]:
    reader = PdfReader(io.BytesIO(raw))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
