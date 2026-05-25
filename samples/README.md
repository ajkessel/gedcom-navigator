# Synthetic GEDCOM Sample

`fictional_genealogy.ged` is a generated, fictional GEDCOM 5.5.1 file for demos, screenshots, manual testing, and unit tests.

The file contains 1000 people, multiple remarriages, multi-child families, two cross-branch marriages, and 50 DNA-flagged people split between `_MTTAG` records and Ancestry-style `PAGE` markers. All names, places, and relationships are synthetic.

Stable anchor records:

- `@I1@` - Maya Lynn Hart, the home-person example.
- `@I11@` - Caleb Hart Lane, Maya's paternal first cousin.
- `@I28@` - Natalie Stone Bell, Maya's maternal second cousin.
- `@F10@` - Caleb and Natalie's cross-branch marriage.
- `@I12@` and `@I29@` - a second paternal-first-cousin/maternal-second-cousin pair.

Regenerate the GEDCOM after changing the generator:

```bash
python dev/generate_sample_gedcom.py
```
