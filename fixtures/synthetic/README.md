# synthetic fixtures

Hand-written documents for cases no account can record: a deprecated Materials Project
summary entry (the API returns none even with `deprecated=True`), and a GNoME-derived entry
(omitted for accounts that have not accepted the GNoME license). Every file here carries a
top-level `"_synthetic": true` marker, and a test asserts no such marker exists under
`fixtures/wire/` or `fixtures/adapters/`. Values in these files are placeholders, not data.
