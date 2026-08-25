"""
The 18 commercial cover sections, transcribed from the broker needs analysis
(`Needs Analysis.pdf` in the repository root) and verified against that PDF —
not against any other codebase. Do not invent sections, do not drop any, and
keep the scope notes faithful to the document: they are what the model reads
when deciding whether a business needs the section.

Also here: the Motor sub-types (from section 14 of the PDF).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class SectionId(str, Enum):
    buildings_combined = "buildings-combined"
    fire = "fire"
    business_interruption = "business-interruption"
    office_contents = "office-contents"
    glass = "glass"
    accounts_receivable = "accounts-receivable"
    fidelity = "fidelity"
    theft = "theft"
    money = "money"
    goods_in_transit = "goods-in-transit"
    electronic_equipment = "electronic-equipment"
    business_all_risks = "business-all-risks"
    group_personal_accident = "group-personal-accident"
    motor = "motor"
    motor_traders = "motor-traders"
    public_liability = "public-liability"
    broadform_liability = "broadform-liability"
    umbrella_liability = "umbrella-liability"


@dataclass(frozen=True)
class CoverSection:
    id: SectionId
    number: int  # section number in the needs analysis, so a user can find it in the PDF
    name: str
    scope: str  # what the section covers, per the needs analysis


COVER_SECTIONS: List[CoverSection] = [
    CoverSection(
        SectionId.buildings_combined, 1, "Buildings Combined",
        "Buildings. May also include public supply connections, rent, liability, "
        "and burst or accidentally damaged geysers.",
    ),
    CoverSection(
        SectionId.fire, 2, "Fire",
        "Assets such as plant, machinery and equipment, contents, and stock in trade. "
        "Fire extinguishing charges and architects' or other professional fees are also included.",
    ),
    CoverSection(
        SectionId.business_interruption, 3, "Business Interruption",
        "Loss of gross profit, gross rentals or revenue; additional increase in cost of "
        "working; wages; fines and penalties for breach of contract. Extensions: prevention "
        "of access; loss from interruption or interference because of damage at the premises "
        "of suppliers, sub-contractors and customers; other events per endorsement; "
        "accidental damage; theft by forcible entry or exit.",
    ),
    CoverSection(
        SectionId.office_contents, 4, "Office Contents",
        "Contents, rent, documents, legal liability documents, and increase in cost of working.",
    ),
    CoverSection(
        SectionId.glass, 5, "Glass",
        "Internal and external glass including mirrors and sign-written glass. Can extend to "
        "boarding up windows, shop fronts, frames, window displays including fixtures and "
        "fittings, burglar alarm strips, wires and vibrators, and the removal and "
        "re-installation of fixtures and fittings.",
    ),
    CoverSection(
        SectionId.accounts_receivable, 6, "Accounts Receivable",
        "Loss or damage to books of account or other business books or records.",
    ),
    CoverSection(
        SectionId.fidelity, 7, "Fidelity",
        "Loss of money and direct financial loss sustained through fraud or dishonesty by an "
        "insured employee. Also covers computer losses.",
    ),
    CoverSection(
        SectionId.theft, 8, "Theft",
        "Loss or damage to business contents from theft accompanied by forcible and violent "
        "entry into or exit from the building, or theft following violence or the threat of "
        "violence such as an armed robbery. Can include damage to the building, including "
        "landlord's fixtures and fittings, and replacing locks and keys following the "
        "disappearance of keys.",
    ),
    CoverSection(
        SectionId.money, 9, "Money",
        "Money held on the premises and in transit to and from the bank; receptacles such as "
        "cash registers, safes and strongrooms; personal accident assault.",
    ),
    CoverSection(
        SectionId.goods_in_transit, 10, "Goods-in-Transit",
        "Loss or damage to goods in transit. Either full cover, or restricted cover for fire, "
        "explosion, collision, derailment and vehicle overturning.",
    ),
    CoverSection(
        SectionId.electronic_equipment, 11, "Electronic Equipment",
        "Standard electronic business equipment such as desktop computers, printers, modems, "
        "scanners, PABXs and servers, plus portable equipment such as laptops and notebooks. "
        "Can extend to increase in cost of working and the reinstatement of data or programmes.",
    ),
    CoverSection(
        SectionId.business_all_risks, 12, "Business All Risks",
        "Loss or damage to equipment anywhere in the world, ranging from commercial "
        "travellers' samples, tools, cameras and CCTV installations to generators and pumps.",
    ),
    CoverSection(
        SectionId.group_personal_accident, 13, "Group Personal Accident / Stated Benefits",
        "Fixed amounts, or amounts relating to annual remuneration, following bodily injury "
        "by accidental, violent, external and visible means to a specified principal, partner, "
        "director or employee, resulting in death, permanent disability, temporary total "
        "disability or medical expenses.",
    ),
    CoverSection(
        SectionId.motor, 14, "Motor",
        "Loss of or damage to business vehicles - motor cars, light delivery vehicles, buses, "
        "trucks, trailers, caravans, motorcycles and special types such as forklifts, "
        "goods-carrying trolleys and quad bikes, extendable to bulldozers, excavators and "
        "cranes - plus liability to third parties.",
    ),
    CoverSection(
        SectionId.motor_traders, 15, "Motor Traders",
        "Damage to vehicles as defined, on and off the premises, subject to restrictions and "
        "exceptions, as well as liability to third parties caused by the vehicle.",
    ),
    CoverSection(
        SectionId.public_liability, 16, "Public Liability",
        "Injury or damage caused by the insured during its business activities.",
    ),
    CoverSection(
        SectionId.broadform_liability, 17, "Broadform Liability",
        "As Public Liability, but wider cover.",
    ),
    CoverSection(
        SectionId.umbrella_liability, 18, "Umbrella Liability",
        "For small and medium commercial enterprises where premiums fall below certain "
        "limits. Indemnity for damages, costs, fees and expenses.",
    ),
]

_BY_ID = {s.id: s for s in COVER_SECTIONS}


def section(section_id: SectionId) -> CoverSection:
    return _BY_ID[section_id]


class MotorSubType(str, Enum):
    comprehensive = "comprehensive"
    third_party_fire_theft = "third-party-fire-theft"
    third_party_only = "third-party-only"


MOTOR_SUB_TYPE_NOTES = {
    MotorSubType.comprehensive:
        "Comprehensive. May include medical expenses following an accident, passenger "
        "liability and contingent liability.",
    MotorSubType.third_party_fire_theft:
        "Third Party, Fire and Theft. No own-damage cover beyond fire and theft.",
    MotorSubType.third_party_only:
        "Third Party only. Liability to third parties only.",
}
