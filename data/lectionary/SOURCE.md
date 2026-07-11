# Lectionary (date to Gospel reference)

`gospels.json` maps each calendar date to the Ordinary-Form Mass **Gospel reference**
(and the English liturgical day name), so the explorer can show "the Fathers on today's
Gospel". We store **only the reference** (which chapter and verses are read, a fact) and
the day name. The verse text itself is served from our public-domain Douay-Rheims, and
the commentary from our Catena Aurea. No third-party reading text, translation, or
arrangement is copied.

## Sources

- **Gospel reference** - AELF (`api.aelf.org`), the universal Roman Ordinary-Form
  lectionary. Cross-checked against USCCB for sample dates (they agree; the Sunday and
  weekday Gospel is universal). Only the citation string is taken.
- **English liturgical day name** - the Church Calendar API (`calapi.inadiutorium.cz`),
  General Roman Calendar in English. Only the celebration title is taken.

## Method and scope

- Built by `ingest/lectionary.py` (stdlib only, resumable). Each Gospel reference is
  normalized to our Douay-Rheims book naming and validated to resolve to real verses we
  hold; the run reports any reference that does not parse or whose verses are missing.
- Window in `gospels.json`: **2026-07-10 through 2027-03-20** (the range AELF currently
  serves). Re-run `python ingest/lectionary.py START END` to extend or refresh; it keeps
  the days already fetched and only fills what is missing.
- A few readings use modern versification that runs one verse past the Douay numbering
  (e.g. Mark 4:41, John 11:57); those verses simply have no Douay text in this corpus and
  are shown as far as the Douay goes. Passion narratives that span two chapters resolve
  the verses within the first chapter. These are noted by the builder, not hidden.
- This is the General Roman Calendar, not a national calendar, so a few national feast
  days may differ; the Gospel of the day is the universal lectionary.
