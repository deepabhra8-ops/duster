/**
 * ProfileMapperJob.jsx - single Profile Mapper job page.
 *
 * The header polls GET /api/job/:id (same JOB_POLL_INTERVAL cadence every
 * other job-polling hook in the app uses) for as long as the job is still
 * queued/running/cancelling, so a job opened mid-run keeps updating without
 * a manual refresh; polling stops once it reaches a terminal status. A live
 * transition from active to done/error/cancelled (never on the very first
 * load, since `prevStatusRef` starts empty) fires exactly one toast for
 * that outcome - the same "job finished" notification ProfileMapper.jsx's
 * table shows, so arriving here from a link (or straight from a bookmark)
 * behaves the same either way. A bad/unknown id shows an error card rather
 * than a fabricated page.
 *
 * Placeholder D (the larger box, "Profile Map Results") holds the Profile
 * Map table, shaped exactly like Sheet 2+ of the real Profile Map workbook
 * (the per-table sheets after "Instructions" -
 * engine/profile_map/profile_map_writer.py's ProfileMapWriter.COLUMNS): one
 * row per profiled column, with its dtype/count/null/distinct stats, CDE
 * flag, applicable rules, rule parameters, and analyst notes, across every
 * table the job profiled. Real once the job is done and has generated
 * results (`hasRealProfile`): fetched as JSON via GET /api/job/:id/profile-map
 * (fetchProfileMap). That endpoint is a plain read of what
 * PipelineService._run_profile_mapper already stored on the job the moment
 * the run finished (ProfileMapResultService.build_rows(), fed the profile
 * mapper engine's in-memory result directly) - no Excel file gets written at
 * run time itself; that only happens on demand (see Download below). Before
 * the job is done - draft/running/error/cancelled - and on a zero-row
 * result, the table shows "No details to show." instead (colSpan across
 * every column, matching the jobs list table's own empty-state convention
 * on ProfileMapper.jsx).
 *
 * The table is split into one tab per source table (derived client-side from
 * the already-fetched rows' `Table` field - no extra request on tab switch),
 * with a horizontally-scrollable tab strip for jobs profiling many tables.
 *
 * Each column group carries its rules, which the analyst can add to (a rule
 * profiling didn't suggest) and delete. Both are staged client-side and applied
 * with any cell edits in one PATCH, so a Save lands whole or not at all.
 *
 * Downloading the workbook is the header's "Download Excel" button. The redesign
 * removed the side rail this used to live in (JobDownloadCard.jsx is no longer
 * rendered by this page). It hits GET /api/job/:id/download/profile, which
 * regenerates the .xlsx from whatever is currently saved (edited or not) on
 * every request - see download_routes.py - so there is no separate "export, then
 * download" step to keep in sync with edits.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchJob, fetchProfileMap, updateProfileMapCells, http, TRANSFER_TIMEOUT } from "../api/api.js";
import { useToast } from "../hooks/useToast.js";
import { JOB_POLL_INTERVAL } from "../constants/appConfig.js";
import { DQ_RULES } from "../constants/dqRules.js";
import { SOURCE_TYPES } from "../constants/sourceTypes.js";
import { fmtDate } from "../utils/helpers.js";
import Pagination from "../components/Pagination.jsx";
import Tabs from "../components/Tabs.jsx";
import StatusPill from "../components/StatusPill.jsx";
import { IconError, IconWarning, IconCheckCircle } from "../components/Icons.jsx";
import RuleEditModal from "../components/profileMapper/RuleEditModal.jsx";
import RuleAddModal from "../components/profileMapper/RuleAddModal.jsx";
import ExpandableColumnRow from "../components/profileMapper/ExpandableColumnRow.jsx";
import "../styles/profile-map-redesign.css";
import {
  Table2,
  Columns3,
  // Rows3 for "Rows Analyzed" and ListChecks for "Detected Rules": a database
  // cylinder and a security shield described where the data lives and a
  // guarantee about it, neither of which is what either card counts.
  Rows3,
  ListChecks,
  Filter,
  MoreVertical,
  Download,
} from "lucide-react";

const ACTIVE_STATUSES = ["queued", "running", "cancelling"];

/** Friendly copy for the Profile Map Results card when there's no real data to show yet, keyed by job status. */
const PROFILE_MAP_STATUS_MESSAGE = {
  draft: "This job hasn't been run yet. Click Run on the Profile Mapper page to generate a profile map.",
  queued: "This job is queued to run - the profile map will appear here once it finishes.",
  running: "This job is still running - the profile map will appear here once it finishes.",
  cancelling: "This job is being cancelled - no profile map will be generated.",
  cancelled: "This job was cancelled before a profile map could be generated.",
  error: "This job failed, so no profile map was generated. Check the log for details.",
};

/**
 * Per-column profiling output. The backend stores one row per column *per rule*,
 * so these values repeat identically across a column's rules - they're rendered
 * once as a rowSpan'd cell covering the whole column group instead of being
 * repeated down the table (see the table body below).
 *
 * Verbatim from ProfileMapWriter.COLUMNS (profile_map_writer.py) minus "Row ID",
 * which is an internal identifier used to key edits (see profileMapRowKey), not
 * something an analyst needs to see or enter. "#" is display-only - it numbers
 * the column groups within the active table's tab.
 */
const PROFILE_MAP_META_COLUMNS = [
  "#",
  "Enabled",
  "Column",
  "Data Type",
  "Total Count",
  "Null Count",
  "Null %",
  "Distinct Count",
  "Unique %",
  "Min Value",
  "Max Value",
  // The body has always rendered a rules badge here (ExpandableColumnRow), but
  // this list never declared it, so the header was one short and every cell from
  // the badge onward rendered under the previous column's heading - which is why
  // "2 rules" appeared beneath CDE and the CDE checkbox had no header at all.
  // PROFILE_MAP_COLUMN_WIDTHS already carried a "Rules" entry for this column.
  "Rules",
  "CDE"
];

const PROFILE_MAP_RULES_COLUMN = "Applicable Rules";
const PROFILE_MAP_PARAMS_COLUMN = "Rule Parameters";
const PROFILE_MAP_NOTES_COLUMN = "Analyst Notes";

const PROFILE_MAP_COLUMNS = PROFILE_MAP_META_COLUMNS;

/**
 * Editable in edit mode, split by what the value actually belongs to.
 *
 * Column-level (Enabled, CDE) describe the column itself, not any one rule - they
 * render as a single merged checkbox and a change writes to every rule row of that
 * column, keeping the merged cell honest about the rows behind it.
 *
 * Rule-level are per-rule. "Applicable Rules" is deliberately absent: profiling
 * chose it, and changing it in place would silently repoint an existing rule's
 * parameters. To apply a rule profiling didn't suggest, add a rule row instead.
 */
const PROFILE_MAP_COLUMN_LEVEL_EDITABLE = new Set(["Enabled", "CDE (X=Yes)"]);
const PROFILE_MAP_RULE_LEVEL_EDITABLE = new Set([
  PROFILE_MAP_PARAMS_COLUMN,
  PROFILE_MAP_NOTES_COLUMN,
]);

/** CDE (X=Yes) is a checkbox in edit mode (X = checked, blank = unchecked) rather than free text - matches
 * the "X=Yes" convention the column header itself already describes and the xlsx source uses. */
const PROFILE_MAP_CDE_COLUMN = "CDE (X=Yes)";
const PROFILE_MAP_ENABLED_COLUMN = "Enabled";

/** The parameter format a rule expects, shown as the placeholder on a new rule row. */
const ruleParameterHint = (ruleId) =>
  (DQ_RULES.find((rule) => rule.id === ruleId)?.params || "").trim();
const isProfileMapCheckboxChecked = (value, col) =>
  col === PROFILE_MAP_ENABLED_COLUMN
    ? String(value || "Y").trim().toUpperCase() === "Y"
    : String(value || "").trim().toUpperCase() === "X";

/** A row's stable identity for draft-edit keying/matching to the backend (row_id, not
 * array position - see profileMapDraftEdits' own comment for why position isn't safe here). */
const profileMapRowKey = (row) => row?.row_id ?? "";

/**
 * Fixed per-column pixel widths, paired with .profile-map-table's
 * table-layout: fixed (global.css) - pins every column's width up front so
 * the header row renders consistently regardless of content. Sized
 * generously enough that every header label (nowrap, global.css) fits on
 * one line - "Distinct Count"/"CDE (X=Yes)" are the widest labels, so those
 * two grew the most from an earlier, data-only sizing pass.
 */
const PROFILE_MAP_COLUMN_WIDTHS = {
  "#": 48,
  "Enabled": 100,
  Column: 150,
  "Data Type": 110,
  "Total Count": 100,
  "Null Count": 100,
  "Null %": 80,
  "Distinct Count": 120,
  "Unique %": 90,
  "Min Value": 100,
  "Max Value": 100,
  "Rules": 120,
  "CDE": 60,
};

export default function ProfileMapperJob() {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [job, setJob] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [columnSearch, setColumnSearch] = useState("");

  const [profileMapRows, setProfileMapRows] = useState([]);
  const [profileMapLoading, setProfileMapLoading] = useState(false);
  const [profileMapError, setProfileMapError] = useState(null);
  // The profile_results_version this page last loaded from the server (fetchProfileMap's own
  // "version" field) - echoed back on Save so the backend can tell "I'm editing against what's
  // actually there right now" apart from "someone else saved a change since I loaded this"
  // (JobService.update_profile_map_cells' optimistic-concurrency guard). Real edits only exist
  // once this is set (>0), so it's also used as a "results are actually editable yet" gate.
  const [profileMapVersion, setProfileMapVersion] = useState(0);

  // Uncommitted cell edits for the 4 editable columns, keyed by profileMapRowKey(row) (row_id - not array position: this table can be re-fetched, e.g. after a version conflict
  // below, and a stale index could then silently point at a different row) - kept apart from
  // profileMapRows (the last-fetched/saved baseline) so Cancel can discard them by just
  // clearing this, without needing to re-fetch. Only holds a row/column entry when its value
  // actually differs from the baseline (see handleProfileMapCellChange) - typing back to the
  // original value drops that cell's entry rather than counting as "unsaved".
  const [profileMapDraftEdits, setProfileMapDraftEdits] = useState({});
  // No longer using whole-table edit mode. Modals handle individual rule editing.
  
  // State for expand/collapse of column rows
  const [expandedColumns, setExpandedColumns] = useState({});
  
  // Modals state
  const [editingRule, setEditingRule] = useState(null); // { line, currentParams, currentNotes }
  const [addingRuleToGroup, setAddingRuleToGroup] = useState(null); // group object
  
  const [savingProfileMapEdits, setSavingProfileMapEdits] = useState(false);

  // Which table's tab is currently shown - kept separate from profileMapRows so
  // switching tabs is a pure client-side filter, never a re-fetch.
  const [activeProfileMapTable, setActiveProfileMapTable] = useState("");

  // Rule rows the analyst has added but not yet saved. `tempKey` is a local render
  // key only - it is never sent as a row_id. The server mints the real id when the
  // row is saved (see the additions payload in handleSaveProfileMapEdits), which is
  // why a new row references its column by `sourceRowId`, an id the server issued.
  const [profileMapNewRows, setProfileMapNewRows] = useState([]);
  const newRowSeq = useRef(0);

  // row_ids of saved rule rows marked for removal. They stay on screen, struck
  // through, until Save - so the delete is reviewable and undoable rather than
  // whipping a row away on a single click.
  const [profileMapRemovedRows, setProfileMapRemovedRows] = useState([]);

  // Status this page last observed for `jobId` - lets a poll tick tell an
  // active -> terminal transition apart from "was already done on load",
  // so the completion toast fires at most once, and never on first paint.
  const prevStatusRef = useRef(null);

  /* Fetch (and, while active, keep polling) the job itself. */
  useEffect(() => {
    let cancelled = false;
    let timerId = null;
    prevStatusRef.current = null;

    async function tick() {
      const { ok, data, error } = await fetchJob(jobId);
      if (cancelled) return;

      if (!ok || !data?.job_id) {
        setLoadError(error || "Job not found");
        return;
      }

      const prevStatus = prevStatusRef.current;
      setJob(data);

      if (prevStatus && ACTIVE_STATUSES.includes(prevStatus) && !ACTIVE_STATUSES.includes(data.status)) {
        const label = data.name || jobId;
        if (data.status === "done") {
          showToast({
            type: "success",
            title: "Job finished",
            message: `"${label}" completed successfully.`,
          });
        } else if (data.status === "error") {
          showToast({
            type: "error",
            title: "Job failed",
            message: `"${label}" ran into a problem and didn't finish. Check the log for details.`,
          });
        } else if (data.status === "cancelled") {
          showToast({ type: "warn", title: "Job cancelled", message: `"${label}" was cancelled.` });
        }
      }
      prevStatusRef.current = data.status;

      if (ACTIVE_STATUSES.includes(data.status)) {
        timerId = setTimeout(tick, JOB_POLL_INTERVAL);
      }
    }

    tick();

    return () => {
      cancelled = true;
      if (timerId) clearTimeout(timerId);
    };
  }, [jobId, showToast]);

  const hasRealProfile = job?.status === "done" && job?.has_profile;
  const sourceNoun = job?.params?.source_type === SOURCE_TYPES.FLAT_FILE ? "file" : "table";

  /* Once the job is done with generated results, load them (View Results
   * step 4b: one call returns job_id/job_name/rows together - see
   * job_routes.py's get_job_profile_map - though this page already has
   * job_id/job_name from the polling effect above and doesn't need to
   * re-read them from here).
   *
   * `failed_tables` names any file/table the run had to skip while keeping the
   * rest (ProfilingEngine.profile) - announced once per load, since the skipped
   * one simply has no tab and would otherwise go unnoticed. */
  useEffect(() => {
    // A fresh fetch (new jobId, or hasRealProfile just flipped) replaces the
    // baseline rows entirely - any in-flight edits against the old baseline
    // no longer apply, so drop them rather than let a stale draft linger
    // against different rows.
    setProfileMapDraftEdits({});
    setProfileMapNewRows([]);
    setProfileMapRemovedRows([]);
    setExpandedColumns({});
    setEditingRule(null);
    setAddingRuleToGroup(null);

    if (!hasRealProfile) {
      setProfileMapRows([]);
      setProfileMapError(null);
      setProfileMapVersion(0);
      return undefined;
    }

    let cancelled = false;
    setProfileMapLoading(true);
    fetchProfileMap(jobId).then(({ ok, data, error }) => {
      if (cancelled) return;
      setProfileMapLoading(false);
      if (!ok) {
        setProfileMapError(error || "Failed to load profile map");
        return;
      }
      setProfileMapError(null);
      setProfileMapRows(data.rows || []);
      setProfileMapVersion(data.version || 0);

      const failed = data.failed_tables || [];
      if (failed.length) {
        const names = failed.map((f) => `"${f.table}"`).join(", ");
        const plural = failed.length === 1 ? "" : "s";
        showToast({
          type: "warn",
          title: `${failed.length} ${sourceNoun}${plural} couldn't be profiled`,
          message:
            `${names} failed and ${failed.length === 1 ? "was" : "were"} skipped. ` +
            `Results for the other ${sourceNoun}s are shown below.`,
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [jobId, hasRealProfile, sourceNoun, showToast]);

  // Download enables only once the results table has actually rendered real rows -
  // matches hasRealProfile, but also waits out the fetch above so a click can't race it.
  // The download itself always regenerates server-side from whatever is currently
  // saved (see download_routes.py), so there's no separate "has this been exported
  // yet" state to track here anymore.
  const canDownloadProfileMap = job?.status === "done" && !profileMapLoading && !profileMapError;

  // One tab per table the job profiled, in first-seen order - derived from the
  // already-fetched rows so switching tabs never triggers a new request.
  const profileMapTableNames = useMemo(() => {
    const names = [];
    const seen = new Set();
    for (const row of profileMapRows) {
      const name = row?.Table || "";
      if (!seen.has(name)) {
        seen.add(name);
        names.push(name);
      }
    }
    return names;
  }, [profileMapRows]);

  // Profiled columns per table, shown in each tab's label - rows are one per
  // column per rule, so this counts distinct column names.
  const profileMapColumnCountByTable = useMemo(() => {
    const columnsByTable = new Map();
    for (const row of profileMapRows) {
      const table = row?.Table || "";
      if (!columnsByTable.has(table)) columnsByTable.set(table, new Set());
      columnsByTable.get(table).add(String(row?.Column ?? ""));
    }
    return new Map([...columnsByTable].map(([table, columns]) => [table, columns.size]));
  }, [profileMapRows]);

  // Keep the active tab valid as the row set changes (new job, fresh fetch) -
  // defaults to the first table, and follows along if the previously active
  // table disappears (e.g. a re-run profiled a different table set).
  useEffect(() => {
    if (profileMapTableNames.length === 0) {
      setActiveProfileMapTable("");
    } else if (!profileMapTableNames.includes(activeProfileMapTable)) {
      setActiveProfileMapTable(profileMapTableNames[0]);
    }
  }, [profileMapTableNames, activeProfileMapTable]);

  /** Distinct profiled columns across every table - rows are one-per-rule, so this
   * is not simply profileMapRows.length. */
  /* "Detected Rules" counted profileMapRows.length - one row per column/rule
     pair - so a profile applying the same three checks to ten columns reported
     30 rules rather than the 3 distinct rules it actually detected. Count the
     distinct rule ids instead, which is what the card's own "Applicable rules"
     subtitle claims. Blank cells are skipped: a row can carry no rule at all. */
  const profileMapDistinctRuleCount = useMemo(
    () =>
      new Set(
        profileMapRows
          .map((row) => String(row?.[PROFILE_MAP_RULES_COLUMN] ?? "").trim())
          .filter(Boolean)
      ).size,
    [profileMapRows]
  );

  const profileMapColumnCount = useMemo(
    () =>
      new Set(
        profileMapRows.map((row) => `${row?.Table ?? ""}.${row?.Column ?? ""}`)
      ).size,
    [profileMapRows]
  );

  const activeProfileMapRows = useMemo(
    () => profileMapRows.filter((row) => (row?.Table || "") === activeProfileMapTable),
    [profileMapRows, activeProfileMapTable]
  );

  // One group per profiled column, in the order the rows arrived. The backend
  // stores a row per column *per rule*, so this is what collapses the repeated
  // profiling stats into a single rowSpan'd cell with the rules listed beside it.
  const profileMapGroups = useMemo(() => {
    const groups = [];
    const byColumn = new Map();

    for (const row of activeProfileMapRows) {
      const column = String(row?.Column ?? "");
      let group = byColumn.get(column);

      if (!group) {
        group = { column, rows: [] };
        byColumn.set(column, group);
        groups.push(group);
      }

      group.rows.push(row);
    }

    return groups;
  }, [activeProfileMapRows]);

  /** Column-name search. Client-side over the already-loaded rows - switching
   *  tables or typing here never costs a request. */
  const visibleProfileMapGroups = useMemo(() => {
    const query = columnSearch.trim().toLowerCase();
    if (!query) return profileMapGroups;
    return profileMapGroups.filter((group) =>
      String(group.column || "").toLowerCase().includes(query)
    );
  }, [profileMapGroups, columnSearch]);

  // Same "real rows are actually on screen" gate Download uses, plus there must be at least
  // one row to edit and a real version to save against (profileMapVersion > 0 - see that
  // state's own comment) - and not mid-Save, so a second click can't race the first request.
  const canEditProfileMap =
    canDownloadProfileMap && profileMapRows.length > 0 && profileMapVersion > 0 && !savingProfileMapEdits;
  const hasUnsavedProfileMapEdits =
    Object.keys(profileMapDraftEdits).length > 0 ||
    profileMapNewRows.length > 0 ||
    profileMapRemovedRows.length > 0;

  /** Current value for one cell: an uncommitted edit if there is one, else the last-fetched/saved value. */
  function profileMapCellValue(row, col) {
    const key = profileMapRowKey(row);
    return profileMapDraftEdits[key]?.[col] ?? row?.[col] ?? "";
  }

  /** Live-updates the draft on every keystroke (all editable-column cells are inputs at once while
   * profileMapEditMode is on, so there's no per-cell "open/commit" step anymore) - drops the cell's
   * draft entry entirely once its value matches the baseline again, rather than keeping a no-op diff. */
  function handleProfileMapCellChange(row, col, value) {
    const key = profileMapRowKey(row);
    const baseline = row?.[col] ?? "";
    setProfileMapDraftEdits((prev) => {
      const rowEdits = { ...(prev[key] || {}) };
      if (value === baseline) {
        delete rowEdits[col];
      } else {
        rowEdits[col] = value;
      }
      const next = { ...prev };
      if (Object.keys(rowEdits).length === 0) {
        delete next[key];
      } else {
        next[key] = rowEdits;
      }
      return next;
    });
  }

  /** Enabled/CDE describe the column, not one rule - so a change to the merged cell
   * writes to every rule row behind it, keeping stored rows consistent with the
   * single checkbox the analyst actually sees. */
  function handleProfileMapColumnLevelChange(group, col, checked) {
    if (col === PROFILE_MAP_ENABLED_COLUMN) {
      if (!checked) {
        const keys = group.rows.map((row) => profileMapRowKey(row));
        setProfileMapRemovedRows((prev) => {
          const next = [...prev];
          for (const key of keys) {
            if (!next.includes(key)) next.push(key);
          }
          return next;
        });

        setProfileMapNewRows((prev) =>
          prev.filter(
            (newRow) =>
              !(newRow.table === activeProfileMapTable && newRow.column === group.column)
          )
        );

        setProfileMapDraftEdits((prev) => {
          const next = { ...prev };
          for (const key of keys) {
            delete next[key];
          }
          return next;
        });
      } else {
        const keys = group.rows.map((row) => profileMapRowKey(row));
        setProfileMapRemovedRows((prev) => prev.filter((k) => !keys.includes(k)));
      }
      return;
    }

    const value = checked ? "X" : "";
    for (const row of group.rows) {
      handleProfileMapCellChange(row, col, value);
    }
  }

  /** Add an empty rule row to a column, for a rule profiling didn't suggest. It stays
   * client-side until Save; the server assigns its real row_id then. */
  function handleAddRuleRow(group) {
    newRowSeq.current += 1;

    setProfileMapNewRows((prev) => [
      ...prev,
      {
        tempKey: `new-${newRowSeq.current}`,
        table: activeProfileMapTable,
        column: group.column,
        sourceRowId: profileMapRowKey(group.rows[0]),
        values: {
          [PROFILE_MAP_RULES_COLUMN]: "",
          [PROFILE_MAP_PARAMS_COLUMN]: "",
          [PROFILE_MAP_NOTES_COLUMN]: "",
        },
      },
    ]);
  }

  function handleNewRuleRowChange(tempKey, col, value) {
    setProfileMapNewRows((prev) =>
      prev.map((newRow) =>
        newRow.tempKey === tempKey
          ? { ...newRow, values: { ...newRow.values, [col]: value } }
          : newRow
      )
    );
  }

  /** Discard one not-yet-saved rule row without touching any other pending edit. */
  function handleRemoveNewRuleRow(tempKey) {
    setProfileMapNewRows((prev) => prev.filter((newRow) => newRow.tempKey !== tempKey));
  }

  /** Drop a saved rule row from the table. It leaves the DB on Save; to bring the
   * rule back, pick it from the Add-rule dropdown, which offers it again now that
   * the column no longer carries it. */
  function handleRemoveSavedRuleRow(row) {
    const rowKey = profileMapRowKey(row);

    setProfileMapRemovedRows((prev) =>
      prev.includes(rowKey) ? prev : [...prev, rowKey]
    );

    // A row on its way out shouldn't also carry pending cell edits to save.
    setProfileMapDraftEdits((prev) => {
      if (!(rowKey in prev)) return prev;
      const next = { ...prev };
      delete next[rowKey];
      return next;
    });
  }

  /** Cancel: discard every uncommitted edit and added row, and leave edit mode. */
  function handleCancelProfileMapEdits() {
    setProfileMapDraftEdits({});
    setProfileMapNewRows([]);
    setProfileMapRemovedRows([]);
  }

  /** Save: sends the draft to PATCH /api/job/:id/profile-map (updateProfileMapCells) - server-validated
   * (editable-field whitelist, length cap, real-rule-ID check - see JobService.update_profile_map_cells'
   * docstring for every case) and persisted onto job["profile_results"], the same JSON a Validator job
   * created from this Profile Mapper job embeds - so a Validator job created *after* this Save picks up
   * these edits; one already created before it doesn't retroactively change (see the conversation this
   * was built from, not repeated here).
   *
   * Sends `profileMapVersion` (what this page last loaded) - a 409 means someone else saved an edit to
   * this same job since then: the response's own rows/version become the new baseline (so the page
   * reflects reality) and the draft/edit mode are deliberately left alone, so the user's in-progress
   * edit isn't silently lost - they can look at what changed and decide whether to retry Save. */
  async function handleSaveProfileMapEdits() {
    if (!hasUnsavedProfileMapEdits) {
      setProfileMapEditMode(false);
      return;
    }

    // The server rejects a rule-less added row anyway; catching it here keeps the
    // user's whole draft intact and names the column they still need to fill in.
    const incomplete = profileMapNewRows.find(
      (newRow) => !newRow.values[PROFILE_MAP_RULES_COLUMN]
    );

    if (incomplete) {
      showToast({
        type: "warn",
        title: "Pick a rule first",
        message: `The rule row added to "${incomplete.column}" needs an applicable rule before it can be saved.`,
      });
      return;
    }

    const edits = Object.entries(profileMapDraftEdits).map(([key, changes]) => {
      return { row_id: key, changes };
    });

    // Resolve each addition against a row of its column that is *surviving* this
    // save - the row it was created from may itself be marked for removal (deleting
    // the suggested rule and adding a different one is one gesture, not two saves).
    // The server keeps a column's last rule, so a survivor always exists.
    const additions = profileMapNewRows.map((newRow) => {
      const survivor = profileMapRows.find(
        (row) =>
          (row?.Table || "") === newRow.table &&
          (row?.Column || "") === newRow.column &&
          !profileMapRemovedRows.includes(profileMapRowKey(row))
      );

      return {
        source_row_id: survivor ? profileMapRowKey(survivor) : newRow.sourceRowId,
        changes: { ...newRow.values },
      };
    });

    setSavingProfileMapEdits(true);
    const result = await updateProfileMapCells(
      jobId,
      profileMapVersion,
      edits,
      additions,
      profileMapRemovedRows
    );
    setSavingProfileMapEdits(false);

    if (result.ok) {
      setProfileMapRows(result.rows);
      setProfileMapVersion(result.version);
      setProfileMapDraftEdits({});
      setProfileMapNewRows([]);
      setProfileMapRemovedRows([]);
      showToast({ type: "success", title: "Profile map saved", message: "Your edits are saved." });
      return;
    }

    if (result.conflict) {
      setProfileMapRows(result.rows);
      setProfileMapVersion(result.version);
      showToast({
        type: "warn",
        title: "Someone else changed this",
        message: "The profile map was updated elsewhere since you loaded it - refreshed to the latest. Your edits are still here; review and Save again.",
      });
      return;
    }

    showToast({ type: "error", title: "Couldn't save", message: result.error || "Failed to save your edits." });
  }

  const handleDownloadProfileMap = async () => {
    setIsDownloading(true);
    showToast({
      type: "info",
      title: "Downloading...",
      message: "Generating .xlsx file...",
    });

    try {
      const res = await http.get(`/job/${jobId}/download/profile`, {
        responseType: "blob",
        // Streamed out of S3 and can be large - not subject to the default cap.
        timeout: TRANSFER_TIMEOUT,
      });
      const blob = new Blob([res.data], { type: res.headers["content-type"] });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `Source_DQ_Profile_Map_${jobId}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);

      showToast({
        type: "success",
        title: "Download complete",
        message: "Profile Map downloaded successfully.",
      });
    } catch (err) {
      console.error("Download failed:", err);
      showToast({
        type: "error",
        title: "Download failed",
        message: "There was an error generating the file.",
      });
    } finally {
      setIsDownloading(false);
    }
  };

  // Scoped by table: two files commonly share a column name like "id", and
  // expanding it in one tab must not expand it in the other.
  const expandKey = (column) => `${activeProfileMapTable}::${column}`;

  const handleToggleExpand = (key) => {
    setExpandedColumns(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  /* Click-away closes whatever column is expanded.
   *
   * An expanded column opens a rules panel several rows tall, and the only way
   * to shut it was to find the same chevron again - which has usually been
   * pushed off screen by the panel it opened. Clicking anywhere outside the
   * grid now closes it, the way every other transient panel in the app behaves.
   *
   * Two things this must NOT treat as "outside":
   *
   *   - The rule Edit/Add dialogs. ModalPortal renders them into <body>, so by
   *     DOM position they are outside the grid while being the most inside
   *     thing there is by intent - without this guard, opening one would
   *     collapse the row it was opened from, and closing it would leave the
   *     user looking at a collapsed table.
   *
   *   - A click that started inside and ended outside (a drag to select text,
   *     or a scrollbar grab). pointerdown fires where the gesture STARTS,
   *     which is what makes that work.
   *
   * Collapsing discards nothing: edits live in profileMapDraftEdits and
   * added/removed rules in their own lists, all keyed by row, none of it tied
   * to whether the panel is on screen. */
  const profileMapGridRef = useRef(null);

  useEffect(() => {
    if (!Object.values(expandedColumns).some(Boolean)) return undefined;

    function handlePointerDown(event) {
      const grid = profileMapGridRef.current;
      if (!grid || grid.contains(event.target)) return;
      if (event.target.closest?.(".modal-overlay")) return;
      setExpandedColumns({});
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [expandedColumns]);

  const handleEditRuleSave = (newValues) => {
    if (!editingRule) return;
    const { key, row } = editingRule;
    
    setProfileMapDraftEdits((prev) => {
      const rowEdits = { ...(prev[key] || {}) };
      
      [PROFILE_MAP_PARAMS_COLUMN, PROFILE_MAP_NOTES_COLUMN].forEach(col => {
        const val = newValues[col];
        const baseline = row?.[col] ?? "";
        if (val === baseline) {
          delete rowEdits[col];
        } else {
          rowEdits[col] = val;
        }
      });

      const next = { ...prev };
      if (Object.keys(rowEdits).length === 0) {
        delete next[key];
      } else {
        next[key] = rowEdits;
      }
      return next;
    });
    setEditingRule(null);
  };

  const rulesTakenForColumn = (group) => {
    if (!group) return new Set();
    const taken = new Set();
    
    group.rows.forEach(row => {
      if (!profileMapRemovedRows.includes(profileMapRowKey(row))) {
        const ruleId = profileMapDraftEdits[profileMapRowKey(row)]?.[PROFILE_MAP_RULES_COLUMN] ?? row[PROFILE_MAP_RULES_COLUMN];
        if (ruleId) taken.add(ruleId);
      }
    });

    profileMapNewRows.forEach(newRow => {
      // Because group doesn't have a table property directly, we compare against activeProfileMapTable
      if (newRow.table === activeProfileMapTable && newRow.column === group.column) {
        const ruleId = newRow.values[PROFILE_MAP_RULES_COLUMN];
        if (ruleId) taken.add(ruleId);
      }
    });
    
    return taken;
  };

  const handleAddRuleSave = (newValues) => {
    if (!addingRuleToGroup) return;
    
    newRowSeq.current += 1;
    setProfileMapNewRows((prev) => [
      ...prev,
      {
        tempKey: `new-${newRowSeq.current}`,
        table: activeProfileMapTable,
        column: addingRuleToGroup.column,
        sourceRowId: profileMapRowKey(addingRuleToGroup.rows[0]),
        values: newValues,
      },
    ]);
    
    setAddingRuleToGroup(null);
  };

  if (loadError) {
    return (
      <section>
        <header className="page-header">
          <h2>Job not found</h2>
        </header>
        <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> {loadError}</div>
      </section>
    );
  }

  if (!job) {
    // Mirrors the LOADED page, with skeletons in place of its contents: same
    // header, same four summary cards, same results card, same table classes and
    // column widths. An approximation is worse than none - the first version of
    // this rendered a bare `tbl` with no summary cards and none of the redesign's
    // chrome, so the page visibly rebuilt itself the moment data arrived.
    return (
      <section className="profile-mapper-job-page">
        <header className="page-header profile-page-header">
          <div className="header-left">
            <h2>
              <span className="skeleton skeleton-heading" aria-label="Loading job" />
            </h2>
            <p className="job-meta">Job Id: {jobId}</p>
            <dl className="job-meta-row">
              {["Started by", "Created at"].map((label) => (
                <div className="job-meta-item" key={label}>
                  <dt>{label}</dt>
                  <dd><span className="skeleton skeleton-text sm" /></dd>
                </div>
              ))}
            </dl>
          </div>
        </header>

        <div className="summary-cards" aria-hidden="true">
          {["Tables", "Columns", "Rows Analyzed", "Detected Rules"].map((label) => (
            <div className="summary-card" key={label}>
              <div className="summary-icon">
                <span className="skeleton" style={{ width: 24, height: 24, display: "block" }} />
              </div>
              <div className="summary-info">
                <h4>{label}</h4>
                <span className="skeleton skeleton-text sm" />
              </div>
            </div>
          ))}
        </div>

        <div className="job-layout profile-mapper-job-layout full-width page-fill">
          <div className="job-layout-main">
            <div
              className="card job-placeholder-box-lg"
              aria-busy="true"
              aria-label="Loading profile map"
            >
              <div className="profile-map-results-body">
                <div className="profile-map-results-titlebar">
                  <div className="card-title">Profile Map Results</div>
                </div>

                <div className="table-scroll">
                  {/* Same classes and colgroup as the real table, so the column
                      widths match and the headers are not squeezed. */}
                  <table className="tbl profile-map-table redesigned profile-map-grid">
                    <colgroup>
                      <col style={{ width: "60px" }} />
                      {PROFILE_MAP_COLUMNS.map((col) => (
                        <col key={col} style={{ width: `${PROFILE_MAP_COLUMN_WIDTHS[col]}px` }} />
                      ))}
                    </colgroup>
                    <thead>
                      <tr>
                        <th className="expand-header">Edit</th>
                        {PROFILE_MAP_COLUMNS.map((col) => (
                          <th key={col}>{col}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Array.from({ length: 6 }).map((_, i) => (
                        <tr key={`boot-skeleton-${i}`} aria-hidden="true">
                          <td><span className="skeleton-cell" /></td>
                          {PROFILE_MAP_COLUMNS.map((col) => (
                            <td key={col}>
                              <span className="skeleton-cell" />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
          {/* No side rail: the redesign moved Download into the header, so the
              loaded page is main-only. The skeleton showing Download/Summary
              cards here was rendering chrome that no longer exists. */}
        </div>
      </section>
    );
  }

  // Sum each distinct table's row count once - profileMapRows repeats a row per
  // column per applicable rule across every profiled table, so picking a single
  // row's "Total Count" (e.g. profileMapRows[0]) only reflected whichever table
  // happened to appear first in the flattened list, not the job's actual total.
  const rowsAnalyzed = (() => {
    const seenTables = new Set();
    let sum = 0;
    for (const row of profileMapRows) {
      const table = row?.Table ?? "";
      if (seenTables.has(table)) continue;
      seenTables.add(table);
      sum += Number(row?.["Total Count"]) || 0;
    }
    return sum;
  })();

  return (
    <section className="profile-mapper-job-page">
      <header className="page-header profile-page-header">
        <div className="header-left">
           <h2>{job.name || "Untitled Job"}</h2>
           <StatusPill status={job.status} />
           <p className="job-meta">
             Job Id: {jobId}
             {job.description ? ` | ${job.description}` : ""}
           </p>
           {/* Who ran this and when. `started` is the API's name for
               started_at, which the jobs table defaults to now() on insert -
               there is no separate created_at column, and the row is inserted
               when the job is created, so this is the creation time. */}
           <dl className="job-meta-row">
             <div className="job-meta-item">
               <dt>Started by</dt>
               <dd>{job.created_by || "-"}</dd>
             </div>
             <div className="job-meta-item">
               <dt>Created at</dt>
               <dd>{fmtDate(job.started)}</dd>
             </div>
           </dl>
        </div>
        <div className="header-actions">
           {hasUnsavedProfileMapEdits && (
              <div className="unsaved-indicator">
                 <span className="dot"></span> Draft
              </div>
           )}
           <button
             type="button"
             className={`btn ${hasUnsavedProfileMapEdits ? "btn-primary" : "btn-secondary"}`}
             disabled={savingProfileMapEdits || !canEditProfileMap}
             onClick={handleSaveProfileMapEdits}
             title={savingProfileMapEdits ? "Saving…" : "Save Profile Map"}
           >
             {/* In-flight feedback in the button itself - a save that takes a
                 few seconds otherwise looks like nothing happened. */}
             {savingProfileMapEdits ? (
               <>
                 <span className="metadata-spinner" aria-hidden="true" style={{ width: "14px", height: "14px" }} />{" "}
                 Saving…
               </>
             ) : (
               "Save Profile Map"
             )}
           </button>

           {/* Lands on the CURRENT Validator flow with this job pre-selected as
               the source. The previous button navigated to /run/validator, the
               pre-V2 run page, which is why it showed a stale UI. Disabled while
               edits are unsaved, since create_validator_draft reads the SAVED
               rows - running now would validate against what is on the server,
               not what is on screen. */}
           <button
             type="button"
             className="btn btn-primary"
             disabled={hasUnsavedProfileMapEdits}
             title={
               hasUnsavedProfileMapEdits
                 ? "Save your profile map before running validation"
                 : "Create a validation job from this profile map"
             }
             onClick={() => navigate(`/validator?sourceJobId=${jobId}`)}
           >
             Run Validation
           </button>

           <div className="dropdown">
             <button
               className={`btn btn-secondary dropdown-toggle${isDownloading ? " btn-busy" : ""}`}
               onClick={handleDownloadProfileMap}
               disabled={!canDownloadProfileMap || isDownloading}
             >
               {/* The side-rail Download card already spun while in flight; this
                   button did not, so a slow export looked like a dead click. */}
               {isDownloading ? (
                 <span className="metadata-spinner" aria-hidden="true" style={{ width: "14px", height: "14px" }} />
               ) : (
                 <Download size={16} />
               )}{" "}
               {isDownloading ? "Downloading…" : "Download Excel"}
             </button>
           </div>
        </div>
      </header>

      {job.status === "done" && !profileMapLoading && !profileMapError && (
      <div className="summary-cards">
        <div className="summary-card">
           <div className="summary-icon"><Table2 size={24} /></div>
           <div className="summary-info">
             <h4>Tables</h4>
             <h2>{profileMapTableNames.length || "-"}</h2>
             <p>From this profile</p>
           </div>
        </div>
        <div className="summary-card">
           <div className="summary-icon"><Columns3 size={24} /></div>
           <div className="summary-info">
             <h4>Columns</h4>
             <h2>{profileMapColumnCount || "-"}</h2>
             <p>Total columns</p>
           </div>
        </div>
        <div className="summary-card">
           <div className="summary-icon"><Rows3 size={24} /></div>
           <div className="summary-info">
             <h4>Rows Analyzed</h4>
             <h2>{rowsAnalyzed ? Number(rowsAnalyzed).toLocaleString() : "-"}</h2>
             <p>Total rows</p>
           </div>
        </div>
        <div className="summary-card">
           <div className="summary-icon"><ListChecks size={24} /></div>
           <div className="summary-info">
             <h4>Detected Rules</h4>
             <h2>{profileMapDistinctRuleCount || "-"}</h2>
             <p>Distinct applicable rules</p>
           </div>
        </div>
      </div>
      )}

      <div className="job-layout profile-mapper-job-layout full-width">
        <div className="job-layout-main">
          <div className="card job-placeholder-box-lg">
            <div className="profile-map-results-body">
              {profileMapRows.some(row => String(row["Applicable Rules"] || "").match(/[,|;]/)) && (
                <div className="alert alert-warn" style={{ margin: "20px 20px 10px", borderRadius: "6px" }}>
                  <IconWarning style={{ verticalAlign: "text-bottom" }} /> <strong>Legacy Profile Map</strong>: This job was profiled before the one-rule-per-row update.
                  Rows containing multiple comma-separated rules cannot be individually parameterized here.
                </div>
              )}

              {/* A tab strip, one tab per table - every table this profile
                  covers is visible at once, which is what makes it obvious how
                  many there are and which one is open. A run carrying a dozen
                  long names would overflow, so the strip scrolls horizontally
                  (.profile-map-table-tabs) rather than wrapping into several
                  rows of chrome above the data. The count stays beside it. */}
              {profileMapTableNames.length > 0 && (
                <div className="profile-map-table-picker">
                  <div className="profile-map-table-tabs">
                    <Tabs
                      tabs={profileMapTableNames.map((name) => ({
                        id: name,
                        label: `${name || "(unnamed table)"} (${profileMapColumnCountByTable.get(name) || 0})`,
                      }))}
                      active={activeProfileMapTable}
                      onChange={setActiveProfileMapTable}
                    />
                  </div>
                  <span className="profile-map-table-count">
                    {profileMapTableNames.length} table{profileMapTableNames.length === 1 ? "" : "s"} in this profile
                  </span>
                </div>
              )}

              <div className="column-profile-header">
                 <div className="column-profile-header-left">
                    <h3>Column Profile</h3>
                    <p>View and configure rules for columns in table "{activeProfileMapTable}"</p>
                 </div>
                 <div className="column-profile-toolbar">
                    {/* Filter / Columns / overflow and the two "All ..." selects
                        were placeholders with no handlers - removed rather than
                        left as controls that do nothing when clicked. */}
                    <input
                      type="text"
                      className="toolbar-search"
                      placeholder="Search columns..."
                      value={columnSearch}
                      onChange={(e) => setColumnSearch(e.target.value)}
                      aria-label="Search columns"
                    />
                 </div>
              </div>

              <div className="table-scroll" ref={profileMapGridRef}>
                <table className="tbl profile-map-table redesigned profile-map-grid">
                  <colgroup>
                    <col style={{ width: "60px" }} />
                    {PROFILE_MAP_COLUMNS.map((col) => (
                      <col key={col} style={{ width: `${PROFILE_MAP_COLUMN_WIDTHS[col]}px` }} />
                    ))}
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="expand-header">Edit</th>
                      {PROFILE_MAP_COLUMNS.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {job.status !== "done" ? (
                      <tr>
                        <td colSpan={PROFILE_MAP_COLUMNS.length} className="empty-state">
                          {PROFILE_MAP_STATUS_MESSAGE[job.status] || "No details to show."}
                        </td>
                      </tr>
                    ) : profileMapLoading ? (
                      Array.from({ length: 6 }).map((_, i) => (
                        <tr key={`skeleton-${i}`} aria-hidden="true">
                          {PROFILE_MAP_COLUMNS.map((col) => (
                            <td key={col}>
                              <span className="skeleton-cell" />
                            </td>
                          ))}
                        </tr>
                      ))
                    ) : profileMapError ? (
                      <tr>
                        <td colSpan={PROFILE_MAP_COLUMNS.length}>
                          <div className="alert alert-err"><IconError style={{ verticalAlign: "text-bottom" }} /> {profileMapError}</div>
                        </td>
                      </tr>
                    ) : profileMapRows.length === 0 ? (
                      <tr>
                        <td colSpan={PROFILE_MAP_COLUMNS.length} className="empty-state">
                          No details to show.
                        </td>
                      </tr>
                    ) : (
                      visibleProfileMapGroups.map((group, groupIndex) => {
                        const pendingRows = profileMapNewRows.filter(
                          (newRow) =>
                            newRow.table === activeProfileMapTable &&
                            newRow.column === group.column
                        );

                        const lines = [
                          ...group.rows
                            .filter(
                              (row) => !profileMapRemovedRows.includes(profileMapRowKey(row))
                            )
                            .map((row) => ({
                              kind: "saved",
                              key: profileMapRowKey(row),
                              row,
                            })),
                          ...pendingRows.map((newRow) => ({
                            kind: "pending",
                            key: newRow.tempKey,
                            newRow,
                          }))
                        ];

                        return (
                          <ExpandableColumnRow
                             key={group.column}
                             groupIndex={groupIndex}
                             group={group}
                             lines={lines}
                             isExpanded={!!expandedColumns[expandKey(group.column)]}
                             onToggleExpand={() => handleToggleExpand(expandKey(group.column))}
                             profileMapDraftEdits={profileMapDraftEdits}
                             profileMapRowKey={profileMapRowKey}
                             handleProfileMapColumnLevelChange={handleProfileMapColumnLevelChange}
                             isProfileMapCheckboxChecked={isProfileMapCheckboxChecked}
                             onEditRule={(line) => setEditingRule({
                                key: line.key,
                                row: line.row || line.newRow.values
                             })}
                             onAddRule={(grp) => setAddingRuleToGroup(grp)}
                             onDeleteSavedRule={handleRemoveSavedRuleRow}
                             onDeleteNewRule={handleRemoveNewRuleRow}
                             profileMapRemovedRows={profileMapRemovedRows}
                          />
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <RuleEditModal
        isOpen={!!editingRule}
        onClose={() => setEditingRule(null)}
        row={editingRule?.row}
        currentParams={editingRule ? profileMapCellValue(editingRule.row, PROFILE_MAP_PARAMS_COLUMN) : ""}
        currentNotes={editingRule ? profileMapCellValue(editingRule.row, PROFILE_MAP_NOTES_COLUMN) : ""}
        onSave={handleEditRuleSave}
      />
      <RuleAddModal
        isOpen={!!addingRuleToGroup}
        onClose={() => setAddingRuleToGroup(null)}
        columnName={addingRuleToGroup?.column}
        dataType={addingRuleToGroup?.rows?.[0]?.["Data Type"]}
        takenRules={addingRuleToGroup ? rulesTakenForColumn(addingRuleToGroup) : new Set()}
        onAdd={handleAddRuleSave}
      />
    </section>
  );
}
