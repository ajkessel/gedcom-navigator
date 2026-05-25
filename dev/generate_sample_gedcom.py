#!/usr/bin/env python3
"""Generate the synthetic GEDCOM sample distributed with GEDCOM Navigator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path


PERSON_TARGET = 1000
DNA_TARGET = 50
DNA_TAG_ID = "@T1@"
SOURCE_ID = "@S1@"

MONTHS = [
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]

GIVEN_NAMES = {
    "F": [
        "Adeline",
        "Bianca",
        "Camille",
        "Daphne",
        "Elena",
        "Fiona",
        "Gemma",
        "Helena",
        "Isabel",
        "Julia",
        "Keira",
        "Lena",
        "Maren",
        "Nora",
        "Opal",
        "Phoebe",
        "Rosalie",
        "Serena",
        "Tessa",
        "Vera",
        "Willa",
        "Zara",
    ],
    "M": [
        "Adrian",
        "Bennett",
        "Caleb",
        "Declan",
        "Elias",
        "Felix",
        "Graham",
        "Holden",
        "Isaac",
        "Jonah",
        "Kieran",
        "Leo",
        "Miles",
        "Nathan",
        "Owen",
        "Pierce",
        "Quentin",
        "Rowan",
        "Silas",
        "Theo",
        "Victor",
        "Wyatt",
    ],
}

MIDDLE_NAMES = [
    "Avery",
    "Blair",
    "Corin",
    "Dale",
    "Ellis",
    "Finch",
    "Gray",
    "Harper",
    "Ives",
    "Jules",
    "Lane",
    "Morgan",
    "Quinn",
    "Reese",
    "Sage",
    "Vale",
]

SURNAMES = [
    "Abbott",
    "Baird",
    "Caldwell",
    "Dawson",
    "Ellery",
    "Fletcher",
    "Garrison",
    "Hollis",
    "Keller",
    "Langford",
    "Marston",
    "Norwood",
    "Prescott",
    "Quincy",
    "Roswell",
    "Sterling",
    "Talmadge",
    "Vaughn",
    "Winslow",
    "Yardley",
]

PLACES = [
    "Cedarford, North Province",
    "Hawthorne Mills, North Province",
    "Riverton Hollow, East Province",
    "Briar Glen, East Province",
    "Larkspur Crossing, West Province",
    "Maple Junction, West Province",
    "Juniper Falls, South Province",
    "Willowmere, South Province",
]


@dataclass
class Person:
    xref: str
    given: str
    middle: str
    surname: str
    sex: str
    birth_year: int
    birth_place: str
    death_year: int | None = None
    famc: list[str] = field(default_factory=list)
    fams: list[str] = field(default_factory=list)
    mttags: list[str] = field(default_factory=list)
    page_markers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.given} {self.middle} {self.surname}".strip()


@dataclass
class Family:
    xref: str
    husb: str | None
    wife: str | None
    marr_year: int | None
    marr_place: str
    children: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SampleTree:
    def __init__(self) -> None:
        self.people: dict[str, Person] = {}
        self.families: dict[str, Family] = {}
        self._next_person = 1
        self._next_family = 1

    def add_person(
        self,
        given: str,
        surname: str,
        sex: str,
        birth_year: int,
        middle: str = "",
        birth_place: str | None = None,
        notes: list[str] | None = None,
    ) -> str:
        xref = f"@I{self._next_person}@"
        self._next_person += 1
        place = birth_place or PLACES[(self._next_person + birth_year) % len(PLACES)]
        person = Person(
            xref=xref,
            given=given,
            middle=middle,
            surname=surname,
            sex=sex,
            birth_year=birth_year,
            birth_place=place,
            death_year=self._death_year(birth_year, self._next_person),
            notes=list(notes or []),
        )
        self.people[xref] = person
        return xref

    def add_family(
        self,
        husb: str | None,
        wife: str | None,
        marr_year: int | None,
        children: list[str] | None = None,
        marr_place: str | None = None,
        notes: list[str] | None = None,
    ) -> str:
        xref = f"@F{self._next_family}@"
        self._next_family += 1
        place = marr_place or PLACES[(self._next_family + (marr_year or 1900)) % len(PLACES)]
        family = Family(
            xref=xref,
            husb=husb,
            wife=wife,
            marr_year=marr_year,
            marr_place=place,
            notes=list(notes or []),
        )
        self.families[xref] = family
        if husb:
            self.people[husb].fams.append(xref)
        if wife:
            self.people[wife].fams.append(xref)
        for child in children or []:
            self.add_child_to_family(xref, child)
        return xref

    def add_child_to_family(self, family_id: str, child_id: str) -> None:
        family = self.families[family_id]
        if child_id not in family.children:
            family.children.append(child_id)
        if family_id not in self.people[child_id].famc:
            self.people[child_id].famc.append(family_id)

    def generated_person(self, sex: str, surname: str, birth_year: int, salt: int) -> str:
        given = GIVEN_NAMES[sex][salt % len(GIVEN_NAMES[sex])]
        middle = MIDDLE_NAMES[(salt * 3 + birth_year) % len(MIDDLE_NAMES)]
        return self.add_person(given, surname, sex, birth_year, middle)

    @staticmethod
    def _death_year(birth_year: int, salt: int) -> int | None:
        if birth_year >= 1946:
            return None
        lifespan = 68 + ((birth_year + salt * 7) % 28)
        death_year = birth_year + lifespan
        if death_year >= 2025:
            return None
        return death_year


def _person_number(xref: str) -> int:
    return int(xref.strip("@I"))


def _family_number(xref: str) -> int:
    return int(xref.strip("@F"))


def build_core_tree(tree: SampleTree) -> list[str]:
    """Create stable named relationships used by docs, tests, and screenshots."""
    maya = tree.add_person(
        "Maya",
        "Hart",
        "F",
        1986,
        "Lynn",
        notes=["Synthetic home person for relationship and DNA-match examples."],
    )
    daniel = tree.add_person("Daniel", "Hart", "M", 1958, "Joseph")
    evelyn = tree.add_person("Evelyn", "Reed", "F", 1960, "Clara")
    jonah = tree.add_person("Jonah", "Hart", "M", 1989, "Reed")
    sophie = tree.add_person("Sophie", "Hart", "F", 1992, "Elise")

    arthur = tree.add_person("Arthur", "Hart", "M", 1930, "Miles")
    beatrice = tree.add_person("Beatrice", "Cole", "F", 1932, "Anne")
    patricia = tree.add_person("Patricia", "Hart", "F", 1956, "Mae")
    raymond = tree.add_person("Raymond", "Hart", "M", 1964, "Cole")
    victor = tree.add_person("Victor", "Lane", "M", 1955, "Graham")
    caleb = tree.add_person(
        "Caleb",
        "Lane",
        "M",
        1984,
        "Hart",
        notes=["Paternal first cousin of Maya Lynn Hart."],
    )
    leah = tree.add_person(
        "Leah",
        "Lane",
        "F",
        1988,
        "Hart",
        notes=["Paternal first cousin of Maya Lynn Hart."],
    )

    laura = tree.add_person("Laura", "Finch", "F", 1965, "Paige")
    nolan = tree.add_person("Nolan", "Hart", "M", 1998, "Finch")
    violet = tree.add_person("Violet", "Hart", "F", 2001, "Finch")
    peter = tree.add_person("Peter", "Moss", "M", 1959, "Alan")
    elena = tree.add_person("Elena", "Moss", "F", 1995, "Reed")

    joseph = tree.add_person("Joseph", "Reed", "M", 1902, "Samuel")
    helen = tree.add_person("Helen", "Price", "F", 1905, "Irene")
    samuel = tree.add_person("Samuel", "Reed", "M", 1934, "Price")
    margaret = tree.add_person("Margaret", "Flynn", "F", 1936, "Rose")
    clara = tree.add_person("Clara", "Reed", "F", 1938, "Price")
    edmund = tree.add_person("Edmund", "Reed", "M", 1942, "Price")
    thomas = tree.add_person("Thomas", "Stone", "M", 1937, "Lee")
    olivia = tree.add_person("Olivia", "Stone", "F", 1963, "Reed")
    grace = tree.add_person("Grace", "Stone", "F", 1966, "Reed")
    eric = tree.add_person("Eric", "Bell", "M", 1961, "Miles")
    natalie = tree.add_person(
        "Natalie",
        "Bell",
        "F",
        1985,
        "Stone",
        notes=["Maternal second cousin of Maya Lynn Hart."],
    )
    owen = tree.add_person(
        "Owen",
        "Bell",
        "M",
        1989,
        "Stone",
        notes=["Maternal second cousin of Maya Lynn Hart."],
    )
    iris = tree.add_person("Iris", "Bell", "F", 1991, "Stone")
    miles = tree.add_person("Miles", "Lane", "M", 2011, "Bell")
    clara_lane = tree.add_person("Clara", "Lane", "F", 2014, "Bell")
    theo = tree.add_person("Theo", "Quill", "M", 2016, "Lane")
    ada = tree.add_person("Ada", "Quill", "F", 2018, "Lane")

    seeds = [
        tree.add_family(daniel, evelyn, 1982, [maya, jonah, sophie]),
        tree.add_family(arthur, beatrice, 1954, [daniel, patricia, raymond]),
        tree.add_family(victor, patricia, 1980, [caleb, leah]),
        tree.add_family(daniel, laura, 1996, [nolan, violet],
                        notes=["Remarriage with children from Daniel Hart's second marriage."]),
        tree.add_family(peter, evelyn, 1993, [elena],
                        notes=["Remarriage with a child from Evelyn Reed's second marriage."]),
        tree.add_family(joseph, helen, 1928, [samuel, clara, edmund]),
        tree.add_family(samuel, margaret, 1957, [evelyn]),
        tree.add_family(thomas, clara, 1959, [olivia, grace]),
        tree.add_family(eric, olivia, 1983, [natalie, owen, iris]),
        tree.add_family(
            caleb,
            natalie,
            2008,
            [miles, clara_lane],
            notes=[
                "Cross-branch marriage: Maya Hart's paternal first cousin married her maternal second cousin."
            ],
        ),
        tree.add_family(
            owen,
            leah,
            2013,
            [theo, ada],
            notes=[
                "Cross-branch marriage: another paternal first cousin/maternal second cousin pairing for Maya Hart."
            ],
        ),
    ]
    return seeds


def expand_tree(tree: SampleTree, seed_families: list[str]) -> None:
    queue: list[tuple[str, int]] = [(family_id, 0) for family_id in seed_families]
    fallback_salt = 0

    while len(tree.people) < PERSON_TARGET:
        if not queue:
            surname = SURNAMES[fallback_salt % len(SURNAMES)]
            husb = tree.generated_person("M", surname, 1860 + fallback_salt % 35, fallback_salt)
            wife = tree.generated_person("F", SURNAMES[(fallback_salt + 7) % len(SURNAMES)],
                                         1862 + fallback_salt % 35, fallback_salt + 11)
            queue.append((tree.add_family(husb, wife, 1884 + fallback_salt % 35), 0))
            fallback_salt += 1

        family_id, generation = queue.pop(0)
        family = tree.families[family_id]
        parents = [tree.people[x] for x in (family.husb, family.wife) if x]
        if not parents:
            continue
        youngest_parent_birth = max(parent.birth_year for parent in parents)
        if youngest_parent_birth > 2002:
            continue

        family_num = _family_number(family_id)
        target_children = 4 + ((family_num + generation) % 3)
        additions = max(0, target_children - len(family.children))

        for child_index in range(additions):
            if len(tree.people) >= PERSON_TARGET:
                return
            sex = "F" if (family_num + child_index + generation) % 2 else "M"
            surname = _family_surname(tree, family)
            birth_year = youngest_parent_birth + 23 + child_index * 3
            salt = family_num * 17 + child_index * 5 + generation
            child = tree.generated_person(sex, surname, birth_year, salt)
            tree.add_child_to_family(family_id, child)

            if birth_year <= 2000 and len(tree.people) < PERSON_TARGET:
                spouse_sex = "F" if sex == "M" else "M"
                spouse_surname = SURNAMES[(salt + 9) % len(SURNAMES)]
                spouse_birth = birth_year + ((salt % 5) - 2)
                spouse = tree.generated_person(spouse_sex, spouse_surname, spouse_birth, salt + 31)
                if sex == "M":
                    new_family = tree.add_family(child, spouse, birth_year + 25 + salt % 6)
                else:
                    new_family = tree.add_family(spouse, child, birth_year + 25 + salt % 6)
                queue.append((new_family, generation + 1))

        if len(tree.people) < PERSON_TARGET and generation <= 3 and family_num % 9 == 0:
            _add_remarriage_branch(tree, family, generation, queue)


def _family_surname(tree: SampleTree, family: Family) -> str:
    if family.husb:
        return tree.people[family.husb].surname
    if family.wife:
        return tree.people[family.wife].surname
    return SURNAMES[_family_number(family.xref) % len(SURNAMES)]


def _add_remarriage_branch(
    tree: SampleTree,
    family: Family,
    generation: int,
    queue: list[tuple[str, int]],
) -> None:
    family_num = _family_number(family.xref)
    remarry_husband = bool(family.husb) and (family_num % 2 == 0 or not family.wife)
    if remarry_husband:
        existing = tree.people[family.husb]
        spouse = tree.generated_person("F", SURNAMES[(family_num + 5) % len(SURNAMES)],
                                       existing.birth_year + 2, family_num + 101)
        new_family = tree.add_family(
            family.husb,
            spouse,
            existing.birth_year + 41 + family_num % 7,
            notes=["Generated remarriage branch with additional children."],
        )
    else:
        existing = tree.people[family.wife]
        spouse = tree.generated_person("M", SURNAMES[(family_num + 8) % len(SURNAMES)],
                                       existing.birth_year - 1, family_num + 103)
        new_family = tree.add_family(
            spouse,
            family.wife,
            existing.birth_year + 39 + family_num % 7,
            notes=["Generated remarriage branch with additional children."],
        )

    for idx in range(1 + family_num % 2):
        if len(tree.people) >= PERSON_TARGET:
            return
        sex = "M" if idx % 2 else "F"
        child_birth = existing.birth_year + 43 + idx * 4
        child = tree.generated_person(sex, _family_surname(tree, tree.families[new_family]),
                                      child_birth, family_num + 150 + idx)
        tree.add_child_to_family(new_family, child)
    queue.append((new_family, generation + 1))


def assign_dna_markers(tree: SampleTree) -> None:
    preferred_names = {
        "Caleb Hart Lane",
        "Natalie Stone Bell",
        "Leah Hart Lane",
        "Owen Stone Bell",
    }
    preferred = [
        xref for xref, person in tree.people.items()
        if person.full_name in preferred_names
    ]
    candidates = [
        xref for xref, person in sorted(tree.people.items(), key=lambda item: _person_number(item[0]))
        if xref not in preferred and person.birth_year <= 2005
    ]

    selected = list(preferred)
    index = 7
    while len(selected) < DNA_TARGET:
        xref = candidates[index % len(candidates)]
        if xref not in selected:
            selected.append(xref)
        index += 19

    for marker_index, xref in enumerate(selected):
        person = tree.people[xref]
        if marker_index < DNA_TARGET // 2:
            person.mttags.append(DNA_TAG_ID)
        else:
            person.page_markers.append(f"AncestryDNA Match to {person.full_name}")

    for xref, person in tree.people.items():
        num = _person_number(xref)
        if DNA_TAG_ID not in person.mttags and num % 40 == 0:
            person.mttags.append("@T2@")
        if DNA_TAG_ID not in person.mttags and num % 55 == 0:
            person.mttags.append("@T3@")


def gedcom_date(year: int, salt: int) -> str:
    return f"{1 + salt % 28} {MONTHS[(salt + year) % len(MONTHS)]} {year}"


def write_gedcom(tree: SampleTree, output: Path) -> None:
    lines = [
        "0 HEAD",
        "1 SOUR GEDCOM-NAVIGATOR-SAMPLE",
        "2 NAME GEDCOM Navigator Synthetic Sample Generator",
        "1 GEDC",
        "2 VERS 5.5.1",
        "2 FORM LINEAGE-LINKED",
        "1 CHAR UTF-8",
        "1 NOTE Synthetic GEDCOM sample. All people, places, and relationships are fictional.",
        f"0 {SOURCE_ID} SOUR",
        "1 TITL Synthetic DNA match citation",
        "0 @T1@ _MTTAG",
        "1 NAME DNA Match",
        "0 @T2@ _MTTAG",
        "1 NAME Research Lead",
        "0 @T3@ _MTTAG",
        "1 NAME Needs Verification",
    ]

    for xref in sorted(tree.people, key=_person_number):
        person = tree.people[xref]
        num = _person_number(xref)
        lines.extend([
            f"0 {xref} INDI",
            f"1 NAME {person.given} {person.middle} /{person.surname}/".replace("  ", " "),
            f"2 GIVN {person.given} {person.middle}".strip(),
            f"2 SURN {person.surname}",
            f"1 SEX {person.sex}",
            "1 BIRT",
            f"2 DATE {gedcom_date(person.birth_year, num)}",
            f"2 PLAC {person.birth_place}",
        ])
        if person.death_year:
            lines.extend([
                "1 DEAT",
                f"2 DATE {gedcom_date(person.death_year, num + 3)}",
                f"2 PLAC {PLACES[(num + 3) % len(PLACES)]}",
            ])
        for note in person.notes:
            lines.append(f"1 NOTE {note}")
        for famc in person.famc:
            lines.append(f"1 FAMC {famc}")
        for fams in person.fams:
            lines.append(f"1 FAMS {fams}")
        for tag in person.mttags:
            lines.append(f"1 _MTTAG {tag}")
        for page in person.page_markers:
            lines.extend([
                f"1 SOUR {SOURCE_ID}",
                f"2 PAGE {page}",
            ])

    for xref in sorted(tree.families, key=_family_number):
        family = tree.families[xref]
        num = _family_number(xref)
        lines.append(f"0 {xref} FAM")
        if family.husb:
            lines.append(f"1 HUSB {family.husb}")
        if family.wife:
            lines.append(f"1 WIFE {family.wife}")
        if family.marr_year:
            lines.extend([
                "1 MARR",
                f"2 DATE {gedcom_date(family.marr_year, num + 13)}",
                f"2 PLAC {family.marr_place}",
            ])
        for child in family.children:
            lines.append(f"1 CHIL {child}")
        for note in family.notes:
            lines.append(f"1 NOTE {note}")

    lines.append("0 TRLR")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate(output: Path) -> None:
    tree = SampleTree()
    seeds = build_core_tree(tree)
    expand_tree(tree, seeds)
    assign_dna_markers(tree)
    write_gedcom(tree, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "samples" / "fictional_genealogy.ged",
        help="Path for the generated GEDCOM file.",
    )
    args = parser.parse_args()
    generate(args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
