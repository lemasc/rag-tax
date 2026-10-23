"""rag.e3: the per-variant table, without files."""

from rag.e3 import group, markdown


def rec(kind, g, f=None, behaviour="na"):
    return dict(id="Q", kind=kind, faithfulness=dict(score=f), relevance=dict(score=0.5),
                rubric=dict(grounded=g, correct=g, useful=g, behaviour=behaviour))


def test_content_group_has_faithfulness_and_behavioural_counts_the_behaviour():
    c = group([rec("normal", 2, 1.0), rec("normal", 0, None)], content=True)
    assert c["n"] == 2 and c["grounded"] == 1.0 and c["faithfulness"] == 1.0 and "behaviour_yes" not in c
    b = group([rec("ask_back", 2, behaviour="yes"), rec("ask_back", 1, behaviour="no")], content=False)
    assert b["behaviour_yes"] == 1 and "faithfulness" not in b


def test_markdown_puts_grounded_of_a_run_without_sources_in_parentheses():
    g = dict(n=1, grounded=1.0, correct=1.0, useful=1.0)
    row = dict(no_sources=True, all=g | dict(behaviour_yes=None), content=g | dict(faithfulness=None, relevance=0.5),
               behavioural=g | dict(behaviour_yes=1))
    md = markdown(dict(n_common=1, dropped=[], skipped=[], rows={"none": row}))
    assert "(1.00)" in md and "reference run's sources" in md
