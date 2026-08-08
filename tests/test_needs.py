"""Needs determination: the model proposes, _repair guarantees a complete
table, and the underwriter's confirmation is what drives assessment."""

from app.models import NeedsDetermination, Requirement, SectionNeed
from app.needs import determine_needs
from app.sections import MotorSubType, SectionId


def _need(section, requirement=Requirement.required, **kw):
    return SectionNeed(section=section, requirement=requirement,
                       reason="stated in the submission", **kw)


def test_missing_sections_are_repaired_to_consider(fake_llm):
    fake_llm.register(NeedsDetermination, NeedsDetermination(
        business_note="A bakery.",
        needs=[_need(SectionId.fire)],
    ))
    determination = determine_needs("some submission")
    assert len(determination.needs) == 18
    by_section = {n.section: n for n in determination.needs}
    assert by_section[SectionId.fire].requirement == Requirement.required
    assert by_section[SectionId.motor].requirement == Requirement.consider
    assert "review manually" in by_section[SectionId.motor].reason


def test_needs_come_back_in_canonical_order_with_duplicates_dropped(fake_llm):
    fake_llm.register(NeedsDetermination, NeedsDetermination(
        needs=[
            _need(SectionId.motor, motor_sub_type=MotorSubType.comprehensive),
            _need(SectionId.fire),
            _need(SectionId.fire, requirement=Requirement.not_applicable),  # duplicate: first wins
        ],
    ))
    determination = determine_needs("some submission")
    sections = [n.section for n in determination.needs]
    assert sections.index(SectionId.fire) < sections.index(SectionId.motor)
    by_section = {n.section: n for n in determination.needs}
    assert by_section[SectionId.fire].requirement == Requirement.required
    assert by_section[SectionId.motor].motor_sub_type == MotorSubType.comprehensive


def test_motor_sub_type_is_stripped_off_other_sections(fake_llm):
    fake_llm.register(NeedsDetermination, NeedsDetermination(
        needs=[_need(SectionId.theft, motor_sub_type=MotorSubType.third_party_only)],
    ))
    determination = determine_needs("some submission")
    by_section = {n.section: n for n in determination.needs}
    assert by_section[SectionId.theft].motor_sub_type is None
