"""Reading the slide summary out of a half-written analysis response."""

from app.services.vlm_output import partial_summary


def test_nothing_before_the_summary_starts() -> None:
    assert partial_summary("") is None
    assert partial_summary('{"summ') is None


def test_summary_so_far() -> None:
    assert partial_summary('{"summary": "Merge sort spl') == "Merge sort spl"


def test_complete_summary_stops_at_its_closing_quote() -> None:
    assert partial_summary('{"summary":"Done.","objects":[') == "Done."


def test_escapes_are_decoded_and_a_cut_off_one_waits() -> None:
    assert partial_summary(r'{"summary": "a \"b\" θ') == 'a "b" θ'
    assert partial_summary('{"summary": "x\\') == "x"
    assert partial_summary(r'{"summary": "x\u03') == "x"
