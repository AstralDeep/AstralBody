# Feature 060 release-evidence fixtures

This corpus models the protected `refs/heads/release-evidence-debt` history without placing live
exception debt in the candidate tree. All identities and payloads are synthetic.

The `history` directories are consecutive immutable create-only changesets. Each transition records
the exact parent and retained-entry digests so a test can reconstruct every snapshot:

1. `00-empty` starts with no debt.
2. `01-debt-a` adds exactly one `debts/<exception_id>.json` entry.
3. `02-resolution-a` retains that debt byte-for-byte and adds exactly one
   `resolutions/<resolution_id>.json` entry backed by later passing evidence.
4. `03-debt-b` retains both prior entries and adds a distinct debt for the same platform/check.

An old resolution therefore cannot satisfy the later debt. `receipts` contains the independently
attested registration/resolution shapes that bind each create-only transition. `requests/legal`
contains immutable pre-review shipping-client outage requests. `requests/illegal` intentionally
contains schema-invalid or policy-ineligible requests and is indexed by `expected-validation.json`.

No fixture contains a credential, real user data, a real approval, or publication authority.
