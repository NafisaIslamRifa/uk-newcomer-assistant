"""GOV.UK pages to ingest for v0.1.

Each entry is a GOV.UK base path (the part after https://www.gov.uk).
The Content API serves the same page at https://www.gov.uk/api/content/<path>.
Multi-part guides (e.g. council-tax) return all their parts in one call.

If a path 404s, the fetch script logs it and moves on. Check the live
site, fix the path, and re-run.
"""

SOURCES = [
    # --- Right to work & immigration status ---
    {"path": "prove-right-to-work", "category": "right_to_work"},
    {"path": "evisa", "category": "right_to_work"},
    {"path": "student-visa", "category": "right_to_work"},
    {"path": "skilled-worker-visa", "category": "right_to_work"},
    {"path": "apply-national-insurance-number", "category": "right_to_work"},

    # --- Right to rent & renting ---
    {"path": "prove-right-to-rent", "category": "renting"},
    {"path": "private-renting", "category": "renting"},
    {"path": "assured-periodic-tenancies-tenants", "category": "renting"},
    {"path": "tenancy-deposit-protection", "category": "renting"},
    {"path": "government/publications/how-to-rent", "category": "renting"},

    # --- Council tax ---
    {"path": "council-tax", "category": "council_tax"},
    {"path": "council-tax-bands", "category": "council_tax"},
    {"path": "apply-council-tax-reduction", "category": "council_tax"},

    # --- Healthcare (GOV.UK side; NHS pages come later) ---
    {"path": "guidance/nhs-entitlements-migrant-health-guide", "category": "healthcare"},
    {"path": "healthcare-immigration-application", "category": "healthcare"},
]
