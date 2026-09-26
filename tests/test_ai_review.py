"""AI review guardrails, tested offline (no API calls)."""
from captable_app.ai_review import AI_NOTE, AIReviewResult, _merge_payload, _verify, apply_image_figures
from captable_app.extract_deck import DeckDump
from captable_app.models import Figure
from captable_app.resolve import resolve_inputs

from conftest import dref, make_cap, make_deck, make_review

WB = {"Summary!D13": "4297529.78 =2772880+(215000+150000+995445)/0.8923"}
DECK = {"Slide 19": "Capital Closed/Committed || $2.4M\nWe’ve already closed $1.5M"}


def test_quote_verification():
    assert _verify({"location": "Summary!D13", "quote": "/0.8923"}, WB, DECK) is True
    assert _verify({"location": "Slide 19", "quote": "We've already closed $1.5M"}, WB, DECK) is True  # curly quote
    assert _verify({"location": "Slide 19", "quote": "raising $7M"}, WB, DECK) is False
    assert _verify({"location": "Slide 20 (image)", "quote": "$2.4M CLOSED"}, WB, DECK) is None


def test_unverifiable_findings_are_discarded_and_image_only_capped():
    res = AIReviewResult(model="m")
    data = {"summary": "s", "image_figures": [{"slide": 20, "metric": "committed", "value": 2.4e6,
                                               "quoted_text": "$2.4M CLOSED"}],
            "findings": [
                {"severity": "HIGH", "title": "real", "detail": "d", "arithmetic": "",
                 "evidence": [{"location": "Summary!D13", "quote": "0.8923"}]},
                {"severity": "HIGH", "title": "invented", "detail": "d", "arithmetic": "",
                 "evidence": [{"location": "Slide 19", "quote": "pre-money of $50M"}]},
                {"severity": "HIGH", "title": "image", "detail": "d", "arithmetic": "",
                 "evidence": [{"location": "Slide 20 (image)", "quote": "$2.4M CLOSED"}]},
            ]}
    _merge_payload(res, data, DeckDump("deck.pptx", "pptx", []), WB, DECK)
    assert [f.title for f in res.findings] == ["[AI] real", "[AI] image"]
    assert res.discarded == ["invented"]
    assert res.findings[1].severity == "MEDIUM"          # image-only evidence cannot be HIGH
    assert res.image_figures[0].note == f"{AI_NOTE}:committed"


def test_ai_image_figures_raise_conflicts_but_never_resolve_inputs():
    cap = make_cap()
    # Deck text states nothing; Claude read an open allocation equal to the cap table's from an image.
    deck = make_deck()
    apply_image_figures(deck, [Figure(500.0, dref("Slide 20 (image, read by Claude)"), note=f"{AI_NOTE}:open_allocation")])
    inp = resolve_inputs(investor=None, check_size=None, share_price=None, commitments_in_before="yes",
                         uncounted_commitments=None, placeholder_mode="release", pre_money=None,
                         cap=cap, deck=deck, review=make_review(cap))
    assert inp.check_size == 500      # resolved by the cap table (trusted), AI figure merely agrees
    # AI figure alone for pre-money: not used; falls back to the implied figure
    deck2 = make_deck()
    apply_image_figures(deck2, [Figure(9e6, dref("Slide 5 (image, read by Claude)"), note=f"{AI_NOTE}:pre_money")])
    inp2 = resolve_inputs(investor=None, check_size=100.0, share_price=None, commitments_in_before="yes",
                          uncounted_commitments=None, placeholder_mode="release", pre_money=None,
                          cap=cap, deck=deck2, review=make_review(cap))
    assert inp2.pre_money == 8000.0
    # AI figure that conflicts with the cap table blocks the default check size
    deck3 = make_deck()
    apply_image_figures(deck3, [Figure(450.0, dref("Slide 20 (image, read by Claude)"), note=f"{AI_NOTE}:open_allocation")])
    inp3 = resolve_inputs(investor=None, check_size=None, share_price=None, commitments_in_before="yes",
                          uncounted_commitments=None, placeholder_mode="release", pre_money=None,
                          cap=cap, deck=deck3, review=make_review(cap))
    assert inp3.check_size is None and any(m.startswith("Check size") for m in inp3.missing)
