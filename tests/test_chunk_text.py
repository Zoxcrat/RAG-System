from src.ingest import CHUNK_OVERLAP, CHUNK_SIZE, chunk_text


def test_empty_or_whitespace_text_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   \n  \t ") == []


def test_text_shorter_than_chunk_size_returns_single_chunk():
    assert chunk_text("short text", chunk_size=500, overlap=100) == ["short text"]


def test_no_empty_chunks_in_result():
    chunks = chunk_text("abcdefghij" * 5, chunk_size=10, overlap=3)
    assert all(c for c in chunks)


def test_chunks_respect_max_size():
    chunk_size = 10
    chunks = chunk_text("abcdefghij" * 10, chunk_size=chunk_size, overlap=3)
    assert all(len(c) <= chunk_size for c in chunks)


def test_consecutive_full_chunks_overlap_by_overlap_chars():
    text = "abcdefghijklmnopqrstuvwxyz0123456789" * 3  # 108 chars, no whitespace
    chunk_size, overlap = 12, 4
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    for i in range(len(chunks) - 1):
        if len(chunks[i]) == chunk_size:
            assert chunks[i][-overlap:] == chunks[i + 1][:overlap]


def test_step_advances_by_size_minus_overlap():
    text = "0123456789" * 5  # 50 chars, no whitespace
    chunk_size, overlap = 10, 2
    step = chunk_size - overlap
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    expected = [text[s : s + chunk_size] for s in range(0, len(text), step)]
    assert chunks == expected


def test_default_constants_have_valid_overlap():
    assert 0 <= CHUNK_OVERLAP < CHUNK_SIZE
