from app.core.search import _clean_query, reciprocal_rank_fusion


def _doc(filename, content):
    return {"filename": filename, "content": content}


def test_clean_query_collapses_whitespace():
    assert _clean_query("  hello   world \n") == "hello world"
    assert _clean_query("") == ""
    assert _clean_query(None) == ""


def test_rrf_ranks_items_present_in_both_lists_highest():
    vec = [_doc("a.txt", "alpha"), _doc("b.txt", "beta")]
    kw = [_doc("b.txt", "beta"), _doc("c.txt", "gamma")]
    fused = reciprocal_rank_fusion(vec, kw)
    # b.txt is top-2 in both lists -> highest fused score
    assert (fused[0]["filename"], fused[0]["content"]) == ("b.txt", "beta")
    # union of all unique items
    assert len(fused) == 3


def test_rrf_dedupes_on_filename_and_content():
    vec = [_doc("a.txt", "x"), _doc("a.txt", "x")]
    assert len(reciprocal_rank_fusion(vec)) == 1


def test_rrf_respects_limit():
    vec = [_doc("a", "1"), _doc("b", "2"), _doc("c", "3")]
    assert len(reciprocal_rank_fusion(vec, limit=2)) == 2


def test_rrf_membership_in_both_lists_beats_lone_top_rank():
    # an item agreed on by both retrievers outranks one that is rank-0 in only
    # a single list — the core reason hybrid retrieval helps.
    vec = [_doc("solo", "1"), _doc("shared", "2")]
    kw = [_doc("shared", "2")]
    fused = reciprocal_rank_fusion(vec, kw)
    assert fused[0]["filename"] == "shared"


def test_rrf_empty():
    assert reciprocal_rank_fusion([], []) == []
