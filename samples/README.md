# Synthetic GEDCOM Sample

`fictional_genealogy.ged` is a generated, fictional GEDCOM 5.5.1 file for demos, screenshots, manual testing, and unit tests.

The file contains 1000 people, multiple remarriages, multi-child families, two cross-branch marriages, and 50 DNA-flagged people split between `_MTTAG` records and Ancestry-style `PAGE` markers. All names, places, and relationships are synthetic.

Every person is given a profile photo via a person-level `OBJE`/`FILE` record pointing into `media/`. The portraits are a fixed pool of 36 illustrated faces assigned round-robin by person number, so the Profile and Graph views show images out of the box. Open `fictional_genealogy.ged` directly (with `media/` alongside it) to see the photos.

## Image credit

The faces in `media/` are **Open Peeps** by Pablo Stanley, generated with [DiceBear](https://www.dicebear.com/styles/open-peeps/). They depict no real people and are dedicated to the public domain under **CC0 1.0** — no attribution required. Regenerate or expand the pool with:

```bash
for i in $(seq 1 36); do n=$(printf "%02d" $i); \
  curl -s "https://api.dicebear.com/9.x/open-peeps/png?seed=navigator-peep-${n}&size=256" \
  -o "samples/media/peep_${n}.png"; done
```

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

## License

While GEDCOM-Navigator is released under the BSD 2-clause license, this sample GEDCOM file only is subject to the Unlicense. It is free and unencumbered content released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org/>
