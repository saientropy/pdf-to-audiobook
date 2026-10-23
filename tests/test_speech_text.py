from audiobook.speech_text import clean_prose, speak_math, split_sentences


def test_citations_are_dropped():
    assert clean_prose("Recent work [1, 2] and others [3-5] agree (Smith et al., 2020).") == \
        "Recent work and others agree."
    assert clean_prose("As shown (Lee and Park, 2024; Doe, 2023), it works.") == "As shown, it works."


def test_footnote_markers_are_dropped():
    assert clean_prose("a sequence task instead.¹") == "a sequence task instead."


def test_abbreviations_and_magnitudes():
    assert clean_prose("See Fig. 3, e.g. the 0.4M model.") == "See Figure 3, for example the 0.4 million model."


def test_symbols_in_prose():
    assert clean_prose("Here θ are the parameters and xᵢ the inputs.") == \
        "Here theta are the parameters and x sub i the inputs."


def test_spoken_math():
    assert speak_math("L(θ) = − (1/N) Σᵢ yᵢ log ŷᵢ (1)") == \
        "L of theta equals minus one over N the sum over i of y sub i log y hat sub i"
    assert speak_math("E = mc²") == "E equals mc squared"
    assert speak_math("a^2 + b^2 = c^2") == "a to the power 2 plus b to the power 2 equals c to the power 2"


def test_split_sentences_keeps_abbreviations():
    assert split_sentences("See Fig. 2 for details. It works! Done.") == \
        ["See Fig. 2 for details.", "It works!", "Done."]
