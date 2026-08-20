import pytest

from services.resume_processor import chunk_text, extract_pdf_text


def test_chunk_text_produces_overlapping_chunks() -> None:
    text = "abcdefghij" * 200  # 2000 chars
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 4
    for c in chunks:
        assert len(c) <= 500
    # Overlap check: second chunk should start with the tail of the first.
    assert chunks[0].endswith(chunks[1][:50])


def test_chunk_text_validates_arguments() -> None:
    with pytest.raises(ValueError):
        chunk_text("hi", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("hi", chunk_size=10, overlap=10)


def test_extract_pdf_text_reads_pypdf_generated_file(tmp_path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = tmp_path / "resume.pdf"
    with out.open("wb") as fh:
        writer.write(fh)

    # Blank page returns empty text, but should not crash.
    text = extract_pdf_text(out)
    assert isinstance(text, str)
