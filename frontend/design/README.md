# Design reference (not shipped code)

This folder holds the source-of-truth mockups from the "Duster Main Screen" Design canvas
(claude.ai artifact) and the "Duster Console" Design System artifact they're built from.
Nothing here is imported by the app — it exists so an editor/agent has exact layout, copy,
states and class names to build from, instead of re-guessing the design from a screenshot
or a prose description.

- `mockups/dashboard-dimensions.dc.html` — the Dashboards ▸ Dimensions page (5 dimension
  score tiles with trend sparklines, lowest-scoring-sources ranking, critical data elements
  with downstream-impact icons and resolve actions, composite trend chart, business impact).
  Implemented as `frontend/src/pages/Dashboards/DimensionsPage.jsx`, built against real data
  where the backend has it (jobs, connections) and a clearly-commented sample-data service
  (`dimensionsService.js`) for the parts it doesn't (per-dimension scores, CDEs, lineage,
  business impact $).
- `mockups/data-sources.dc.html` — the Data sources drill-down (source list + the five
  observability pillars: Freshness, Volume, Distribution, Schema changes, Lineage impact).
  Implemented as `frontend/src/pages/Dashboards/DataSourcesPage.jsx` — same real/sample split
  (real connections list, sample `dataSourcesService.js` for pillar telemetry).
- `mockups/connections.dc.html` — the Connections list page: connections grouped by category
  section (Warehouses & lakehouses / Databases / Lakes & query engines / a "Suggested for
  you" section for not-yet-connected sources), plus a wide "Add connection" sheet with a
  category rail + tile grid covering the full connector catalog — six categories (Cloud
  warehouses & lakehouses, Relational & transactional databases, Data lakes & query engines,
  Transformation & orchestration tools, BI & dashboards, SaaS applications & data catalogs),
  36 sources total. The category rail's counts reflect the real catalog size even though only
  one category panel (Warehouses & lakehouses, 7 sources) is shown expanded in this static
  pass. **Not implemented yet.**
- `mockups/connection-form-postgres.dc.html`, `connection-form-redshift.dc.html`,
  `connection-form-dbt-cloud.dc.html` — dedicated per-connector "Add connection" screens,
  reached by clicking a tile in the catalog sheet above. This replaced an earlier
  "2 shared archetypes" design: **every connector gets its own screen with only its own
  fields**, not a shared template. These three are concrete, fully-built examples (using the
  real field names from `backend/services/connectors/*.py` — see each file's
  `required_fields`); the rest of the catalog (Snowflake, BigQuery, MySQL, Tableau, Kafka,
  etc.) still needs the same treatment, one dedicated screen per connector, following this
  pattern. **Not implemented yet.**

## How to read a `.dc.html` file

These are authored for Claude's "Design" canvas tool, not as real HTML pages. When reading
one, ignore two things that only matter to that editor:

- `<script src="./support.js"></script>` in `<head>` — canvas-editor plumbing, not app code.
- The trailing `<script type="text/x-dc" data-dc-script ...>` block — editor tweak-panel
  wiring, not real component logic.

Everything that matters is inside `<x-dc>...</x-dc>` (the actual markup — real layout,
copy, states, class names) and `<helmet><style>...</style></helmet>` (the page's CSS, using
the same custom properties as `frontend/src/design-system/tokens.css`, e.g. `var(--accent)`,
`var(--space-4)`). Cross-page links (`<a href="Other.dc.html">`) show which screen a control
navigates to.

## Source of truth

- Design System (tokens + component specs + usage rules): `frontend/src/design-system/` is
  the already-ported copy. If it and a mockup ever disagree, the mockup's *content and
  states* win (it's the newer, more detailed pass); the *token values* in
  `design-system/tokens.css` are authoritative since they were copied 1:1 from the source
  artifact.
- Design canvas artifact (private, claude.ai): all six pages above live at the "Duster Main
  Screen" artifact. Ask in a Claude Code or claude.ai session for the current link if you
  need to view or extend it directly rather than from this exported copy.
