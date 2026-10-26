# Glossary

## German → English (from ITSG's "Translation Assistance" sheet, plus additions)

| German | English |
|---|---|
| Entgeltersatzleistung (EEL) | income replacement benefit |
| Bescheinigung / Entgeltbescheinigung | notification / pay certificate |
| Meldung | report |
| Fehlzeit wegen Krankheit | paid sick leave, times of incapacity for work |
| Arbeitsunfähigkeit (AU) | incapacity for work (sick leave) |
| Arbeitsunfähigkeitsbescheinigung | sick note / doctor's certificate |
| eAU | electronic sick note |
| Krankengeld | sickness benefit (paid by the health insurer) |
| Mutterschaftsgeld | maternity benefit |
| Übergangsgeld | transitional benefit (during rehabilitation) |
| Verletztengeld | injury benefit (accident insurance) |
| Vorerkrankungszeiten | prior illness periods |
| Vorerkrankungsanfrage | prior-illness request (employer → health insurer) |
| Lohnfortzahlung / Entgeltfortzahlung (EFZ) | sick pay, continued payment of wages (employer pays up to 6 weeks) |
| §23c SGB IV | income during periods of receiving sickness benefit |
| Beitragsbemessungsgrenze | contribution ceiling |
| Sozialversicherungsbeitrag | social insurance contribution |
| Sozialversicherungsträger (SVT) | social security institution |
| Krankenkasse (KK) | health insurance fund |
| Arbeitgeber (AG) | employer |
| Arbeitnehmer (AN) | employee, insured worker |
| Meldepflichtige | persons subject to reporting obligations |
| Lohn / Arbeitslohn / Arbeitsentgelt | income / wages |
| Systemuntersuchung | system review |
| Spezifikationen prüfen | check whether a program meets all applicable specifications |
| Entgeltabrechnungsprogramm | payroll software (a system-tested program) |
| Ausfüllhilfe | filling aid (simple tool for manual entry) |
| Testfall | test case |
| Datensatz (DS) | data record |
| Datenbaustein (DB) | data block (a sub-record appended to a Datensatz) |
| Grundstellung | default value (zeros for numeric fields, spaces for alphanumeric fields) |
| Abgabegrund | submission reason (message type code) |
| Stornierung | cancellation |
| Gemeinsame Grundsätze (GG) | common principles (the binding legal framework) |
| Gemeinsames Rundschreiben (GR) | joint circular from the insurance associations (interpretation guidance) |
| Verfahrensbeschreibung | procedure description (field-by-field spec) |
| DTA EEL | *Datenaustausch Entgeltersatzleistungen*: the EEL data exchange procedure (§107 SGB IV) |
| Daumenkriterium | literally "thumb criterion"; a criterion ITSG has marked specially in the example. Ask ITSG what the label means |

## Abgabegrund: submission-reason codes

Source: Verfahrensbeschreibung §3.1.18, GG_EEL §2.

**Employer → insurer (AG)**

| Code | Meaning |
|---|---|
| 01 | Pay certificate, health insurance (KV), for sickness benefit (*Krankengeld*) |
| 02 | Pay certificate KV, child sickness benefit (home care or co-admission with a hospitalised child) |
| 03 | Pay certificate KV, maternity benefit |
| 04 | Pay certificate KV, sickness benefit for co-admission to hospital accompanying a person with a disability |
| 11 | Pay certificate, pension insurance (RV), transitional benefit, medical rehabilitation |
| 12 | Pay certificate RV, transitional benefit, participation in working life |
| 21 | Pay certificate, accident insurance (UV), injury benefit |
| 22 | Pay certificate UV, transitional benefit |
| 23 | Pay certificate UV, child injury benefit |
| 31 | Pay certificate, Federal Employment Agency (BA), transitional benefit |
| **41** | **Request for prior-illness periods** (*Anforderung Vorerkrankungsmitteilungen*) |
| 42 | Request for end of the income replacement benefit |
| 51 | Amount of contributory income (§23c SGB IV) |
| 73 | Reply: number of released working days |
| 88 | Cancellation of a record |
| 99 | Change of reporting office or system change |

**Insurer → employer (KK / SVT)**

| Code | Meaning |
|---|---|
| **61** | **Reply with prior-illness periods** |
| 62 | Notification of the end of the income replacement benefit |
| 66 | Reply: wrong submission reason |
| 67 | Wrong health insurer / unknown person |
| 71 | Amount of the income replacement benefit |
| 72 | Request for number of released working days |

## Record and block names

| Name | Meaning |
|---|---|
| VOSZ / NCSZ | Header (*Vorlaufsatz*) and trailer (*Nachlaufsatz*) of a transmission file |
| DSKO | Communication record: sender and contact details |
| **DSLW** | **Main EEL record** (*Leistungswesen*). Carries the Abgabegrund |
| DBNA | Name |
| DBAN | Address |
| DBAL | General data (employment begin and end, sick-pay end…) |
| DBAE | Pay data (gross and net pay per period) |
| DBZA | Working hours |
| DBEE | End of income replacement benefit |
| DBAW | Absences without pay |
| DBFR | Release from work for a sick or injured child |
| DBUN | Work, school or kindergarten accident |
| DBMU | Pay certificate for maternity benefit |
| **DBVO** | **Prior illness periods** |
| DBHE | Amount of income replacement benefit |
| DBBE | Contributory income (§23c) |
| DBLT | Extra data for transitional benefit (participation in working life) |
| DBSF | Extra data for seafarers |
| DBTK | Extra data for short-time work (*Kurzarbeit*) |
| DBAP | Contact person |
| DBID | Identification data (file references, Reference ID) |
| DBSD | Cancellation data |

Other identifiers: **DSID** = Datensatz-ID (a UUID per record), **DSID-UR** = original record ID
(used in a cancellation), **REF-ID** = reference ID (links a reply to its request), **AZVU** =
*Aktenzeichen Verursacher* (the sender's own file reference), **BBNR** = Betriebsnummer
(company number), **VSNR** = Versicherungsnummer (social-insurance number).
