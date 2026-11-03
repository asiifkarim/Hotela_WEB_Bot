"""The retriever: threshold, de-duplication, language boost and hybrid ranking.

The rules that matter:

* nothing below the similarity threshold is ever returned;
* the same section is not returned twice;
* a chunk written in the visitor's script is nudged up, not forced up;
* BM25 may re-order the candidates, but it may never introduce one the
  vector store considered too far away.
"""

from app.rag.retriever import retrieve


class Embedder:
    def embed_one(self, text):
        return [1.0, 0.0]


class Collection:
    def query(self, **kwargs):
        return {"documents": [["good", "weak", "duplicate"]], "metadatas": [[{"file": "a", "section": "one"}, {"file": "b", "section": "two"}, {"file": "a", "section": "one"}]], "distances": [[0.1, 0.8, 0.2]]}


class HybridCollection:
    """A collection with a BM25 index over its own documents."""

    def __init__(self, documents, metadatas, distances, kb_version="hybrid-test"):
        self.documents = documents
        self.metadatas = metadatas
        self.distances = distances
        self.metadata = {"kb_version": kb_version}

    def count(self):
        return len(self.documents)

    def get(self, include=None, limit=None):
        return {
            "documents": list(self.documents),
            "metadatas": list(self.metadatas),
            "ids": [str(index) for index in range(len(self.documents))],
        }

    def query(self, **kwargs):
        count = kwargs.get("n_results") or len(self.documents)
        return {
            "documents": [list(self.documents[:count])],
            "metadatas": [list(self.metadatas[:count])],
            "distances": [list(self.distances[:count])],
        }


def test_retriever_applies_threshold_and_deduplicates():
    result = retrieve(Collection(), Embedder(), "query", top_k=3, min_similarity=0.35)
    assert [item.text for item in result] == ["good"]
    assert result[0].similarity == 0.9


def test_the_candidate_pool_can_be_wider_than_the_answer():
    collection = HybridCollection(
        [f"chunk {index}" for index in range(5)],
        [{"file": "f", "section": str(index)} for index in range(5)],
        [0.1, 0.2, 0.3, 0.4, 0.5],
        kb_version="candidate-pool",
    )
    result = retrieve(collection, Embedder(), "query", top_k=2, min_similarity=0.35, candidate_k=5, hybrid=False)
    assert len(result) == 2
    assert result[0].similarity > result[1].similarity


def test_the_script_boost_nudges_a_chunk_in_the_visitors_script():
    english = "Is there a free trial?\nYes, seven days."
    urdu = "کیا مفت ٹرائل ملتا ہے؟\nجی ہاں، سات دن۔"
    collection = HybridCollection(
        [english, urdu],
        [{"file": "faq.md", "section": "en"}, {"file": "faq.md", "section": "ur"}],
        [0.40, 0.42],
        kb_version="script-boost",
    )
    result = retrieve(
        collection,
        Embedder(),
        "کیا مفت ٹرائل ملتا ہے؟",
        top_k=2,
        min_similarity=0.35,
        script_boost=0.05,
        hybrid=False,
    )
    assert result[0].text == urdu


def test_bm25_can_reorder_the_candidates():
    """A chunk the vector store ranked low can be the best lexical match."""
    best_vector = "Hotela is a hotel and restaurant management platform by IdeoMetriX."
    best_lexical = "How many branches one plan covers:\nA fixed number of branches per plan."
    middle = "The price per branch and the price per plan."
    collection = HybridCollection(
        [best_vector, best_lexical, middle],
        [
            {"file": "faq.md", "section": "What is Hotela?"},
            {"file": "rooms_pricing.md", "section": "How many branches one plan covers"},
            {"file": "rooms_pricing.md", "section": "Price per branch"},
        ],
        [0.50, 0.55, 0.60],
        kb_version="hybrid-order",
    )
    result = retrieve(
        collection,
        Embedder(),
        "how many branches can one plan cover",
        top_k=3,
        min_similarity=0.35,
        hybrid=True,
    )
    assert result[0].text == best_lexical
    assert all(item.source == "vector+bm25" for item in result)


def test_bm25_cannot_introduce_a_chunk_below_the_threshold():
    far = "A chunk about something completely different: invoices, taxes, VAT."
    collection = HybridCollection(
        [far],
        [{"file": "invoices.md", "section": "What is not documented about invoices"}],
        [0.90],  # similarity 0.10, far below the threshold
        kb_version="hybrid-threshold",
    )
    result = retrieve(
        collection,
        Embedder(),
        "how many branches can one plan cover invoices taxes",
        top_k=3,
        min_similarity=0.35,
        hybrid=True,
    )
    assert result == []


def test_the_duplicate_text_of_two_sections_is_returned_once():
    collection = HybridCollection(
        ["Same body text", "Same body text"],
        [{"file": "a.md", "section": "one"}, {"file": "b.md", "section": "two"}],
        [0.1, 0.2],
        kb_version="dupe",
    )
    result = retrieve(collection, Embedder(), "query", top_k=3, min_similarity=0.35, dedupe=True, hybrid=False)
    assert len(result) == 1


def test_a_nan_distance_is_skipped():
    collection = HybridCollection(
        ["broken", "good"],
        [{"file": "a", "section": "1"}, {"file": "b", "section": "2"}],
        [float("nan"), 0.2],
        kb_version="nan",
    )
    result = retrieve(collection, Embedder(), "query", top_k=3, min_similarity=0.35, hybrid=False)
    assert [item.text for item in result] == ["good"]
