"""
Excel / CSV import and export for the live modules (UX roadmap item 4, 17 Sep 2026).

    conditions.py   the register's small condition language, server-side
    fields.py       which fields a sheet carries, and cell -> stored value
    workbook.py     reading XLSX / XLS / CSV; writing templates and exports
    importer.py     preview and commit, through each module's own create route

Decided with the user on 17 Sep 2026:
  * Leads import at Stage 0 or 1 only — a later stage has gates and criteria an
    import would skip, so those leads are moved forward in the app.
  * Opportunities and Deals are export-only. Both are born by conversion; an
    imported one would have no parent Lead.
  * An import is all-or-nothing, and is always previewed first.
  * The uploaded file is read and discarded, never stored.
"""
