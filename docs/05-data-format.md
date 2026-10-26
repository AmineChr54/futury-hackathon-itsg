# DTA EEL Data Format

DTA EEL messages are **fixed-width text records**: ISO-8859-1 encoding, CRLF line endings, positions
are 1-based. Every field has a fixed position, length, type (`n` numeric, `an` alphanumeric) and an
M/m flag (mandatory/optional). Unused fields carry the **Grundstellung** (default value): zeros for
numeric fields, spaces for alphanumeric fields. Dates use the format `jhjjmmtt`, i.e. `YYYYMMDD`.

Field definitions: Verfahrensbeschreibung DTA EEL v13.4, §3.

## File structure

A transmission file looks like this:

```
VOSZ  header (Vorlaufsatz)            ← transmission envelope
DSKO  communication record            ← sender and contact
DSLW  main EEL record + data blocks   ← one line: DSLW base (224 chars) + DBNA + DBVO + DBAP + DBID …
NCSZ  trailer (Nachlaufsatz)          ← record count
```

The data blocks (DBxx) are **appended to the DSLW on the same line**. Each starts with its 4-letter
ID. Which blocks must be present depends on the **Abgabegrund**.

## Annotated sample: `TEEL0-Test1-DBVO`

Offsets were verified by slicing the actual file. Line lengths: VOSZ 105, DSKO 403, **DSLW 981**,
NCSZ 63.

### DSLW base record (positions 1–224, §3.1)

| Pos | Len | Field | Value in sample | Meaning |
|---|---|---|---|---|
| 001–004 | 4 | KENNUNG | `DSLW` | Record ID |
| 005–009 | 5 | VERFAHREN | `LEIST` | Procedure |
| 010–024 | 15 | ABSENDERNUMMER | `99302811` | Sender (company number) |
| 025–039 | 15 | EMPFAENGERNUMMER | `00000000` | Receiver (default value here) |
| 040–041 | 2 | VERSION-NR | `13` | Record version |
| 042–061 | 20 | DATUM-ERSTELLUNG | `20260214094108000000` | Created 14.02.2026 09:41:08 |
| 062 | 1 | FEHLER-KENNZ | `0` | Error flag |
| 063 | 1 | FEHLER-ANZAHL | `0` | Error count |
| 064–075 | 12 | VSNR | `17241280Q497` | Social-insurance number |
| 076–083 | 8 | GEBURTSDAT | `19801224` | Date of birth |
| 084–098 | 15 | BBNR-VU | `99302811` | Company number of the sender |
| 099–134 | 36 | DATENSATZ-ID | `11111111-2222-AAAA-EEEE-111111111111` | Record UUID (matches step 1 of the sequence) |
| 135–141 | 7 | PRODUKT-IDENTIFIER | `7654321` | **ID of the system-tested software product** |
| 142–149 | 8 | MODIFIKATIONS-IDENTIFIER | `66666XXX` | Software modification/version ID |
| 150–169 | 20 | DATUM-VERARBEITUNG | `000…0` | Forwarding timestamp (default value) |
| 170–184 | 15 | BBNR-KK | `00000000` | Health insurer's company number |
| 185–199 | 15 | BBNR-ABRECHNUNGSSTELLE | spaces | Payroll office (e.g. a tax advisor) |
| 200 | 1 | RUECKMELDUNG-EEL | `N` | Reply with benefit amount requested? |
| **201–202** | 2 | **ABGABEGRUND** | **`41`** | **Prior-illness request** |
| 203–204 | 2 | KORR-ABGABEGRUND | `00` | Corrected Abgabegrund (only for 66) |
| 205 | 1 | ABRECHNUNGSPROGRAMM | `1` | 1 = system-tested payroll program |
| 206–224 | 19 | (block flags) | `JNNNNNNNNNJNNNNNJJN` | J/N flags for which data blocks follow. Not commented in the Verfahrensbeschreibung; the layout is in the record description (Datensatzbeschreibung) |

### DBNA: name

`DBNA` + family name `Mustermann` + first name `Peter` (padded fields, 125 chars).

### DBVO: prior illness periods (§3.12, 232 chars here)

| Pos | Len | Field | Value | Rule for an employer report |
|---|---|---|---|---|
| 001–004 | 4 | KENNUNG | `DBVO` | |
| 005 | 1 | GRUNDAV | `1` | 1 = AU due to illness, 2 = medical rehab, 3 = for transitional benefit |
| 006–013 | 8 | AU-AB-AG | `20260311` | Start of current AU as known to the employer |
| 014–021 | 8 | AU-AB-SV | `00000000` | **Must be the default value** when the employer sends it (the insurer fills it) |
| 022 | 1 | KZ-AK-AU | `0` | **Must be the default value** from the employer (the insurer sets 4 = AU not on file) |
| 023–030 | 8 | 12-MONATSFRIST-AB | `00000000` | **Must be the default value** from the employer (the insurer fills it) |
| 031–032 | 2 | ANZAHL-AU | `04` | Number of repeating groups that follow |

**Repeating group (50 chars × ANZAHL-AU):**

| Offset | Len | Field | Employer report |
|---|---|---|---|
| +00 | 8 | BEGINN-AU-nn | prior AU start |
| +08 | 8 | ENDE-AU-nn | prior AU end |
| +16 | 1 | KZ-NACHWEIS-nn | default value (the insurer sets 1 / 2 / 4 = fully / partly / not on file) |
| +17 | 8 | TEIL-NACHWEIS-AU-BEGINN-nn | default value |
| +25 | 8 | TEIL-NACHWEIS-AU-ENDE-nn | default value |
| +33 | 1 | KZ-AU-nn | default value (the insurer sets 1 = creditable, 2 = not creditable, 3 = under review, 5 = partly creditable) |
| +34 | 8 | TEIL-ANR-AU-BEGINN-nn | default value |
| +42 | 8 | TEIL-ANR-AU-ENDE-nn | default value |

**The four groups in the sample:**

| nn | Begin | End |
|---|---|---|
| 1 | 2026-03-01 | 2026-03-03 |
| 2 | 2025-12-01 | 2025-12-03 |
| 3 | 2025-10-01 | 2025-10-17 |
| 4 | 2025-07-14 | 2025-07-15 |

Newest first ✔, all four chained periods present ✔, all insurer-only fields at their default value ✔.
This file **passes** the content criteria from [04-example-test-case-dbvo.md](04-example-test-case-dbvo.md).

### DBAP: contact person (§3.18)

Contact person `Mia Testfrau`, phone `069-8700`, email `systemuntersuchung@itsg.de`, company
`Testfirma Qualitätskontrolle`, address in Offenbach.

### DBID: identification data (§3.19)

| Pos | Len | Field | Value |
|---|---|---|---|
| 005–024 | 20 | AKTENZEICHEN-SV | spaces (for the insurer's use) |
| 025–044 | 20 | AKTENZEICHEN-VERURSACHER (AZVU) | `1234-5678-007` |
| 045–080 | 36 | REFERENZ-ID | spaces (set in replies, pointing to the request's DSID) |

### VOSZ / DSKO / NCSZ

- `VOSZ AGEEL 99302811 … 20260214 000001 ITSG GmbH … 01`: header with the procedure `AGEEL`
  (employer → EEL), sender, date and file sequence number.
- `DSKO LEIST 99302811 …`: sender's communication data (Mia Testfrau, Offenbach, phone, email).
- `NCSZ AGEEL 99302811 … 20260214 000001 … 01`: trailer with the record count.

The VOSZ, DSKO and NCSZ layouts are defined in the general communication specs, which were **not
provided**. To parse them precisely we need those layouts from ITSG, or we infer them from the
samples.

## Gaps for the parser

- DSLW positions 206–224 (block-presence flags) are not commented in the Verfahrensbeschreibung.
- The full layouts of VOSZ, DSKO, NCSZ, DBNA and DBAP are only partly commented.
- We have only **one** sample output file, so we'll need to synthesise more, including deliberately
  broken variants.
