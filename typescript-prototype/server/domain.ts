/**
 * Shared vocabulary for the prototype: the cover sections offered on the
 * commercial line, the sample submissions, and the shapes the model returns.
 *
 * The cover sections are transcribed from the broker needs analysis at
 * docs/NEEDS ANALYSIS - NO SIGNATURE.pdf. Do not invent sections, do not drop
 * any, and keep the scope notes faithful to that document - they are what the
 * model reads when deciding whether a business needs the section.
 *
 * The front end imports these types too, so keep this file dependency-free.
 */

export interface CoverSection {
  id: string;
  /** Section number in the needs analysis, so a user can find it in the PDF. */
  number: number;
  name: string;
  /** What the section covers, per the needs analysis. */
  scope: string;
}

export const COVER_SECTIONS: CoverSection[] = [
  {
    id: "buildings-combined",
    number: 1,
    name: "Buildings Combined",
    scope:
      "Buildings. May also include public supply connections, rent, liability, and burst or accidentally damaged geysers.",
  },
  {
    id: "fire",
    number: 2,
    name: "Fire",
    scope:
      "Assets such as plant, machinery and equipment, contents, and stock in trade.",
  },
  {
    id: "business-interruption",
    number: 3,
    name: "Business Interruption",
    scope:
      "Loss of gross profit, gross rentals or revenue; additional increase in cost of working; wages; fines and penalties for breach of contract. Extensions: prevention of access; loss from interruption or interference because of damage at the premises of suppliers, sub-contractors and customers; other events per endorsement; accidental damage; theft by forcible entry or exit.",
  },
  {
    id: "office-contents",
    number: 4,
    name: "Office Contents",
    scope:
      "Contents, rent, documents, legal liability documents, and increase in cost of working.",
  },
  {
    id: "glass",
    number: 5,
    name: "Glass",
    scope:
      "Internal and external glass including mirrors and sign-written glass. Can extend to boarding up windows, shop fronts, frames, window displays including fixtures and fittings, burglar alarm strips, wires and vibrators, and the removal and re-installation of fixtures and fittings.",
  },
  {
    id: "accounts-receivable",
    number: 6,
    name: "Accounts Receivable",
    scope:
      "Loss or damage to books of account or other business books or records.",
  },
  {
    id: "fidelity",
    number: 7,
    name: "Fidelity",
    scope:
      "Loss of money and direct financial loss sustained through fraud or dishonesty by an insured employee. Also covers computer losses.",
  },
  {
    id: "theft",
    number: 8,
    name: "Theft",
    scope:
      "Loss or damage to business contents from theft accompanied by forcible and violent entry into or exit from the building, or theft following violence or the threat of violence such as an armed robbery. Can include replacing locks and keys following the disappearance of keys.",
  },
  {
    id: "money",
    number: 9,
    name: "Money",
    scope:
      "Money held on the premises and in transit to and from the bank; receptacles such as cash registers, safes and strongrooms; personal accident assault.",
  },
  {
    id: "goods-in-transit",
    number: 10,
    name: "Goods-in-Transit",
    scope:
      "Loss or damage to goods in transit. Either full cover, or restricted cover for fire, explosion, collision, derailment and vehicle overturning.",
  },
  {
    id: "electronic-equipment",
    number: 11,
    name: "Electronic Equipment",
    scope:
      "Standard electronic business equipment such as desktop computers, printers, modems, scanners, PABXs and servers, plus portable equipment such as laptops and notebooks. Can extend to increase in cost of working and the reinstatement of data or programmes.",
  },
  {
    id: "business-all-risks",
    number: 12,
    name: "Business All Risks",
    scope:
      "Loss or damage to equipment anywhere in the world, generators and pumps.",
  },
  {
    id: "group-personal-accident",
    number: 13,
    name: "Group Personal Accident / Stated Benefits",
    scope:
      "Fixed amounts, or amounts relating to annual remuneration, following bodily injury by accidental, violent, external and visible means to a specified principal, partner, director or employee, resulting in death, permanent disability, temporary total disability or medical expenses.",
  },
  {
    id: "motor",
    number: 14,
    name: "Motor",
    scope:
      "Loss of or damage to business vehicles - motor cars, light delivery vehicles, buses, trucks, trailers, caravans, motorcycles and special types such as forklifts, goods-carrying trolleys and quad bikes, extendable to bulldozers, excavators and cranes - plus liability to third parties.",
  },
  {
    id: "motor-traders",
    number: 15,
    name: "Motor Traders",
    scope:
      "Damage to vehicles as defined, on and off the premises, subject to restrictions and exceptions, as well as liability to third parties caused by the vehicle.",
  },
  {
    id: "public-liability",
    number: 16,
    name: "Public Liability",
    scope:
      "Injury or damage caused by the insured during its business activities.",
  },
  {
    id: "broadform-liability",
    number: 17,
    name: "Broadform Liability",
    scope: "As Public Liability, but wider cover.",
  },
  {
    id: "umbrella-liability",
    number: 18,
    name: "Umbrella Liability",
    scope:
      "For small and medium commercial enterprises where premiums fall below certain limits. Indemnity for damages, costs, fees and expenses.",
  },
];

/**
 * Motor sub-types. A business with vehicles needs one chosen, and the choice
 * changes what is worth assessing - own-damage exposure only matters under
 * comprehensive cover.
 */
export const MOTOR_SUB_TYPES = [
  {
    id: "comprehensive",
    label: "Comprehensive",
    note: "May include medical expenses following an accident, passenger liability and contingent liability.",
  },
  {
    id: "third-party-fire-theft",
    label: "Third Party, Fire and Theft",
    note: "No own-damage cover beyond fire and theft.",
  },
  {
    id: "third-party-only",
    label: "Third Party only",
    note: "Liability to third parties only.",
  },
] as const;

export const MOTOR_SECTION_ID = "motor";

/**
 * Seed vocabulary for driver slugs. Kept deliberately small and reused across
 * sections: the point is that one weakness shows up in several sections at
 * once, which only works if the model names it the same way each time.
 */
export const DRIVER_VOCABULARY = [
  "unsecured-overnight-parking",
  "no-vehicle-tracking",
  "no-driver-vetting",
  "maintenance-not-logged",
  "single-premises-dependency",
  "no-fire-detection",
  "no-sprinklers",
  "combustible-stock",
  "hot-work-on-site",
  "poor-housekeeping",
  "no-cctv",
  "perimeter-security-only",
  "public-access-to-premises",
  "cash-on-premises",
  "cash-in-transit",
  "high-value-portable-equipment",
  "no-data-backup",
  "unsegregated-financial-duties",
  "staff-vetting-gaps",
  "high-staff-turnover",
  "key-person-dependency",
  "supplier-concentration",
  "loss-history-frequency",
  "manual-handling-and-machinery-injury-exposure",
];

export interface Sample {
  id: string;
  label: string;
  submission: string;
}

export const SAMPLES: Sample[] = [
  {
    id: "brackenfell-bakery",
    label: "Mabuza Bakeries (multi-exposure)",
    submission: `Applicant: Mabuza Bakeries (Pty) Ltd
Trade: Industrial bakery and confectionery, wholesale to supermarkets and spaza shops, plus a small retail counter open to the public
Years trading: 11
Premises: Single leased industrial unit, Brackenfell, Western Cape. Landlord insures the structure; the applicant is responsible for contents, fittings and its own improvements.
Construction: Brick walls, steel trusses, corrugated iron roof, one internal cold room
Floor area: 1,850 square metres
Occupancy: Sole occupant. Adjoining unit is a furniture upholsterer.
Annual turnover: growing steadily, single site, no alternative production facility identified
Plant and machinery: 3 x gas-fired deck ovens, 2 x industrial mixers, dough sheeter, packaging line, walk-in cold room with two compressors
Stock: Flour and sugar in bulk bags, packaging film, cooking oil in drums, finished product held under 48 hours
Fire protection: 11 x 9kg extinguishers, 2 hose reels serviced annually, no automatic detection, no sprinklers
Hot work: Oven servicing and occasional welding repairs done on site by an external contractor, no permit system
Housekeeping: Flour dust swept at end of shift, oil drums stored beside the packaging line, skip emptied twice weekly
Glass: Retail counter has a large sign-written shopfront window onto the street
Security: Palisade fencing, alarm linked to armed response, no CCTV, night watchman on weekends only
Staff: 38 permanent, 6 seasonal over December. Bookkeeper handles invoicing, supplier payments and bank reconciliation.
Staff turnover: high among packing staff, roughly a third replaced each year
Staff vetting: ID and reference check on hire for permanent staff, none for seasonal
Vehicles: 6 x 1-ton refrigerated panel vans, 2 x light delivery bakkies, 1 x forklift used in the yard
Vehicle drivers: 9 drivers, licence checked on hire, no repeat verification, no telematics fitted
Overnight parking: vans parked in the yard behind the palisade fence; 2 vans taken home by drivers
Vehicle maintenance: serviced at a local workshop when due, no internal inspection log
Deliveries: own vans deliver finished product daily to supermarket depots and spaza shops across the Cape metro
Cash handling: retail counter takes cash, roughly a day's takings held in a floor safe, banked by the office manager twice weekly in her own car
Electronic equipment: 6 desktops, 2 laptops taken off site by the sales reps, a server in the office, PABX, and touchscreen tills at the counter
Data: production and accounting records kept on the office server, backed up to an external drive kept in the same office
Debtors book: supermarket accounts invoiced on 30 days, ledger maintained on the server
Public access: retail counter open to walk-in customers during business hours
Key people: founder-owner runs production planning and holds the supermarket relationships personally
Claims history: 1 burglary claim (2022, stock and a laptop), 1 own-damage vehicle claim (2023), 1 employee hand injury on the sheeter (2021), no fire claims
Cover history: continuous, no cancellations`,
  },
  {
    id: "swift-couriers",
    label: "Swift Couriers (fleet-heavy)",
    submission: `Applicant: Swift Couriers (Pty) Ltd
Trade: Same-day parcel courier, business-to-business
Years trading: 6
Premises: Leased depot unit with a small office, Midrand, Gauteng. Landlord insures the building.
Location of operations: Gauteng, primarily Johannesburg CBD, Midrand and Kempton Park
Fleet size: 18 vehicles (14 x 1-ton panel vans, 4 x light delivery bakkies)
Average vehicle age: 5 years
Annual distance per vehicle: approximately 62,000 km
Hours of operation: 06h00 to 20h00, Monday to Saturday
Drivers: 21 permanent drivers, 3 casual relief drivers
Driver screening: licence check on hire, no repeat verification
Youngest driver age: 21
Telematics: fitted to 11 of 18 vehicles, reports reviewed monthly
Overnight parking: 12 vehicles at the fenced depot with a guard, 6 taken home by drivers
Maintenance: serviced at franchise dealers per schedule, no internal inspection log
Goods carried: general parcels for third-party clients, occasional cellphone handsets for a retail client
Office contents: 4 desktops, a server, PABX, counter and shelving in the depot office
Cash handling: none, all clients invoiced on account
Staff: 26 total including 3 office staff; one administrator handles invoicing and payments
Claims history: 7 own-damage claims in 3 years, 1 hijacking (vehicle recovered), 2 third-party liability claims
Previous insurer: cover continuous, no cancellations`,
  },
  {
    id: "kaap-timber",
    label: "Kaap Timber (property-heavy)",
    submission: `Applicant: Kaap Timber Supplies CC
Trade: Timber and board merchant, cutting and edging on site
Premises: Owner-occupied single-storey warehouse with attached retail counter, Bellville, Western Cape
Construction: Brick walls, steel roof trusses, corrugated iron roof
Floor area: 2,400 square metres
Year built: 1994, rewired 2019
Occupancy: Sole occupant, adjoining unit is a panel beater
Stock: Sawn timber, chipboard, adhesives and solvents in a separate side store
Dust extraction: Fitted to the cutting saw, filters cleaned quarterly
Fire protection: 9 x 9kg extinguishers, 2 hose reels, no sprinklers, no fire detection
Housekeeping: Offcuts and sawdust swept daily, skip emptied weekly
Security: Palisade fencing, alarm linked to armed response, no CCTV
Glass: Sign-written shopfront to the retail counter
Staff: 14 permanent, 2 casual
Vehicles: 2 x 3-ton flatbed trucks used to deliver timber to sites
Cash handling: retail counter takes cash, banked daily by the owner
Electronic equipment: 3 desktops, a point-of-sale terminal, no server
Public access: retail counter open to trade and walk-in customers
Flood exposure: Not in a mapped floodline, site drains to a municipal stormwater channel
Business interruption: Wants cover, single site, no alternative premises identified
Claims history: 1 burglary claim (2021, tools), no fire claims`,
  },
];

/* ------------------------------------------------------------------ *
 * Stage 1: needs determination
 * ------------------------------------------------------------------ */

export type Requirement = "required" | "consider" | "not-applicable";

export const REQUIREMENTS: Requirement[] = [
  "required",
  "consider",
  "not-applicable",
];

export interface SectionNeed {
  sectionId: string;
  requirement: Requirement;
  /** One line, grounded in the submission. */
  reason: string;
  /** Only for the Motor section. */
  motorSubType: string | null;
}

export interface NeedsAssessment {
  /** The model's one-line read of the business, for orientation. */
  businessNote: string;
  needs: SectionNeed[];
}

/* ------------------------------------------------------------------ *
 * Stage 2: per-section risk assessment
 * ------------------------------------------------------------------ */

export interface ProposedMetric {
  name: string;
  /** The model picks its own scale; this is whatever it chose. */
  assessedLevel: string;
  /** How the model describes its own scale for this metric. */
  scale: string;
  reasoning: string;
  /** Verbatim quote or field reference from the submission. */
  evidence: string;
  /** Short slugs naming the underlying facts about the business. */
  drivers: string[];
  /** True when accumulated memory shaped this metric. */
  memoryInfluenced: boolean;
  /** Which remembered correction(s) shaped it; null when fresh reasoning. */
  memoryBasis: string | null;
}

export interface Proposal {
  /** Model's one-line note on how it used memory overall. */
  memoryNote: string;
  metrics: ProposedMetric[];
}

/* ------------------------------------------------------------------ *
 * Memory - scoped per cover section
 * ------------------------------------------------------------------ */

export type CorrectionAction = "accepted" | "edited" | "rejected" | "added";

export interface MemoryEntry {
  id: string;
  at: string;
  action: CorrectionAction;
  /** Metric name after the human's edit (or as proposed / added). */
  metricName: string;
  /** Level after the human's edit (or as proposed / added). Null for rejected. */
  assessedLevel: string | null;
  /** What the model originally proposed, when the human changed it. */
  proposedName: string | null;
  proposedLevel: string | null;
  /** Free-text note from the underwriter explaining the correction. */
  note: string | null;
  /** Short label for the submission this correction came from. */
  submissionRef: string;
}

export function findSection(id: string): CoverSection | undefined {
  return COVER_SECTIONS.find((s) => s.id === id);
}
