"""The 18-section taxonomy is transcribed from Needs Analysis.pdf — these
tests pin the invariants a faithful transcription must have."""

from app.sections import (COVER_SECTIONS, DRIVER_VOCABULARY, SectionId,
                          normalise_slug, normalise_slugs, section)


def test_exactly_eighteen_sections_numbered_in_pdf_order():
    assert len(COVER_SECTIONS) == 18
    assert [s.number for s in COVER_SECTIONS] == list(range(1, 19))
    assert len({s.id for s in COVER_SECTIONS}) == 18


def test_section_names_match_the_needs_analysis():
    names = [s.name for s in COVER_SECTIONS]
    assert names[0] == "Buildings Combined"
    assert names[13] == "Motor"
    assert names[17] == "Umbrella Liability"


def test_every_enum_member_has_a_section():
    for sid in SectionId:
        assert section(sid).id == sid


def test_driver_vocabulary_is_normalised_and_unique():
    assert len(set(DRIVER_VOCABULARY)) == len(DRIVER_VOCABULARY)
    for slug in DRIVER_VOCABULARY:
        assert normalise_slug(slug) == slug


def test_slug_normalisation_groups_near_misses():
    assert normalise_slug("No CCTV") == "no-cctv"
    assert normalise_slug("  no_cctv ") == "no-cctv"
    assert normalise_slug("no--cctv!") == "no-cctv"
    assert normalise_slugs(["No CCTV", "no-cctv", "", "   "]) == ["no-cctv"]
