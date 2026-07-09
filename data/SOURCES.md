# Sources, rights, and provenance

This file is the integrity backbone of Catena. Every text in the corpus is listed here with its exact edition, translator, license, and the reasoning for its rights status. **No text enters `data/` until it has an entry here with a verified license.**

Rule: if a text's redistribution rights are unclear, it does not ship. We reference and cite it, we do not redistribute it.

---

## Included: public domain

### Summa Theologica (St. Thomas Aquinas)
- **Translation:** Fathers of the English Dominican Province, second and revised edition, 1920-1922 (Benziger Bros. printing widely dated 1947).
- **License:** Public domain. The translation was published 1920-22; the translators worked as a body ("Fathers of the English Dominican Province") and the work is long out of copyright in the US and EU (published >95 years ago; all contributors' work of this era is public domain).
- **Confirmed by:** Online Library of Liberty and CCEL both host it as public domain. <https://oll.libertyfund.org/titles/province-the-summa-theologica-of-st-thomas-aquinas-part-i-10-vols>
- **Source edition used for ingest:** _to be recorded at ingest time_ (candidate sources: CCEL structured edition, New Advent). We record the exact source URL and retrieval date per unit in the manifest.
- **Attribution redistributed with the text:** "St. Thomas Aquinas, Summa Theologica, trans. Fathers of the English Dominican Province, 2nd rev. ed. (1920-22). Public domain."

### Church Fathers (roadmap)
- **Editions:** Philip Schaff (ed.), *Ante-Nicene Fathers*, *Nicene and Post-Nicene Fathers* (Series 1 and 2), 1885-1900.
- **License:** Public domain (published pre-1929; editor and translators long deceased, works out of copyright).
- **Status:** not yet ingested. Rights confirmed in principle; source edition to be pinned before ingest.

### Douay-Rheims Bible (roadmap)
- **Edition:** Challoner revision (18th c.).
- **License:** Public domain.
- **Status:** not yet ingested.

### Clementine Vulgate (roadmap)
- **Edition:** 1592 Sixto-Clementine.
- **License:** Public domain.
- **Status:** not yet ingested.

### Older encyclicals and council documents (roadmap)
- **Scope:** pre-1930 English translations only, verified per-document.
- **License:** public domain where the translation itself predates the copyright window. **Each document verified individually** - a modern re-translation of an old encyclical is NOT public domain even if the encyclical is old.
- **Status:** not yet ingested.

---

## Excluded: copyrighted - permission track

### Catechism of the Catholic Church
- **Rights holder:** United States Conference of Catholic Bishops (USCCB) and Libreria Editrice Vaticana (LEV). Copyright on both the 1994 English and 1992 French translations.
- **The rule (USCCB):** use of fewer than 5,000 words does not require permission (with the copyright notice); **use of more than 5,000 words made available to the public at no cost requires written permission from the USCCB.** The full Catechism is ~180,000 words.
- **Source:** <https://www.usccb.org/committees/catechism/use-catechism-catholic-church>
- **Decision:** **We do NOT redistribute the Catechism text.** It is not in this corpus. We are pursuing written permission from USCCB for non-commercial, open, educational redistribution as a separate track (see `docs/` permission-request draft). Until and unless that permission is granted in writing, the Catechism stays out.
- **What we may still do without permission:** reference paragraph numbers and structure (facts, not the copyrighted expression), and quote individual paragraphs under the fair-use / <5,000-word allowance with the required copyright notice. Any such use carries the notice.

### Modern encyclical translations, modern Bible translations (RSV-CE, NABRE, ESV-CE, etc.)
- **License:** copyrighted. **Excluded.** Not redistributed. Use the public-domain Douay-Rheims / Vulgate instead, or pursue per-publisher permission.

---

## Provenance recorded per unit

Every ingested unit records, in its manifest entry: `source_url`, `source_edition`, `translator`, `license`, and `retrieved` (ISO date). This makes the whole corpus auditable back to where each word came from.
