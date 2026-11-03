from pathlib import Path

from app.rag.chunker import REQUIRED_FRONT_MATTER, chunk_markdown, is_kb_document, kb_documents, load_all_chunks, parse_front_matter

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb"
FAQ = KB / "faq.md"


def test_faq_is_chunked_one_question_at_a_time():
    _, body = parse_front_matter(FAQ.read_text(encoding="utf-8"))
    questions = [line for line in body.splitlines() if line.startswith("## ")]
    chunks = chunk_markdown(FAQ, "version")
    assert len(chunks) == len(questions)
    assert all(" > " not in chunk.metadata["section"] for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


def test_only_canonical_topic_files_are_indexed():
    indexed = {path.name for path in kb_documents(KB)}
    assert indexed == {
        "app_how_to.md",
        "bookings.md",
        "customers.md",
        "faq.md",
        "finances.md",
        "glossary.md",
        "invoices.md",
        "policies.md",
        "rooms_pricing.md",
    }
    assert not is_kb_document(KB / "GAPS.md")
    assert not is_kb_document(KB / "archive" / "website-2026-10-02" / "faq.md")


def test_every_indexed_file_has_the_required_front_matter():
    for path in kb_documents(KB):
        metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
        missing = [key for key in REQUIRED_FRONT_MATTER if not metadata.get(key)]
        assert not missing, f"{path.name} is missing {missing}"
        assert metadata["topic"] == path.stem, f"{path.name} topic is {metadata['topic']}"
        assert body.strip()
        assert "TODO" not in body and "CONFLICT" not in body


def test_chunks_carry_topic_and_audience_metadata():
    chunks = load_all_chunks(KB, "version")
    assert chunks
    for chunk in chunks:
        assert chunk.metadata["topic"]
        assert chunk.metadata["audience"] in {"visitor", "maintainer", "staff"}
        assert chunk.metadata["kb_version"] == "version"


def test_plans_are_indexed_with_comparison():
    chunks = load_all_chunks(KB, "version")
    assert any(chunk.metadata["section"] == "comparison" for chunk in chunks)
    assert any("Hotela Dine" in chunk.text for chunk in chunks)
