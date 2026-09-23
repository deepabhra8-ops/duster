import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchJob, fetchProfileMap, updateProfileMapCells, http, TRANSFER_TIMEOUT } from "../api/api.js";
import { useToast } from "../hooks/useToast.js";
import { JOB_POLL_INTERVAL } from "../constants/appConfig.js";
import { DQ_RULES } from "../constants/dqRules.js";
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
  Rows3,
  ListChecks,
  Filter,
  MoreVertical,
  Download,
} from "lucide-react";

const ACTIVE_STATUSES = ["queued", "running", "cancelling"];

const PROFILE_MAP_STATUS_MESSAGE = {
  draft: "This job hasn't been run yet. Click Run on the Profile Mapper page to generate a profile map.",
  queued: "This job is queued to run - the profile map will appear here once it finishes.",
  running: "This job is still running - the profile map will appear here once it finishes.",
  cancelling: "This job is being cancelled - no profile map will be generated.",
  cancelled: "This job was cancelled before a profile map could be generated.",
  error: "This job failed, so no profile map was generated. Check the log for details.",
};

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
  "Rules",
  "CDE"
];

const PROFILE_MAP_RULES_COLUMN = "Applicable Rules";
const PROFILE_MAP_PARAMS_COLUMN = "Rule Parameters";
const PROFILE_MAP_NOTES_COLUMN = "Analyst Notes";

const PROFILE_MAP_COLUMNS = PROFILE_MAP_META_COLUMNS;

const PROFILE_MAP_COLUMN_LEVEL_EDITABLE = new Set(["Enabled", "CDE (X=Yes)"]);
const PROFILE_MAP_RULE_LEVEL_EDITABLE = new Set([
  PROFILE_MAP_PARAMS_COLUMN,
  PROFILE_MAP_NOTES_COLUMN,
]);

const PROFILE_MAP_CDE_COLUMN = "CDE (X=Yes)";
const PROFILE_MAP_ENABLED_COLUMN = "Enabled";

const ruleParameterHint = (ruleId) =>
  (DQ_RULES.find((rule) => rule.id === ruleId)?.params || "").trim();
const isProfileMapCheckboxChecked = (value, col) =>
  col === PROFILE_MAP_ENABLED_COLUMN
    ? String(value || "Y").trim().toUpperCase() === "Y"
    : String(value || "").trim().toUpperCase() === "X";

const profileMapRowKey = (row) => row?.row_id ?? "";

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
  const [profileMapVersion, setProfileMapVersion] = useState(0);

  const [profileMapDraftEdits, setProfileMapDraftEdits] = useState({});

  const [expandedColumns, setExpandedColumns] = useState({});

  const [editingRule, setEditingRule] = useState(null);
  const [addingRuleToGroup, setAddingRuleToGroup] = useState(null);
  
  const [savingProfileMapEdits, setSavingProfileMapEdits] = useState(false);

  const [activeProfileMapTable, setActiveProfileMapTable] = useState("");

  const [profileMapNewRows, setProfileMapNewRows] = useState([]);
  const newRowSeq = useRef(0);

  const [profileMapRemovedRows, setProfileMapRemovedRows] = useState([]);

  const prevStatusRef = useRef(null);

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

  useEffect(() => {
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
          title: `${failed.length} table${plural} couldn't be profiled`,
          message:
            `${names} failed and ${failed.length === 1 ? "was" : "were"} skipped. ` +
            `Results for the other tables are shown below.`,
        });
      }
    });

    return () => {
      cancelled = true;
    };
  }, [jobId, hasRealProfile, showToast]);

  const canDownloadProfileMap = job?.status === "done" && !profileMapLoading && !profileMapError;

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

  const profileMapColumnCountByTable = useMemo(() => {
    const columnsByTable = new Map();
    for (const row of profileMapRows) {
      const table = row?.Table || "";
      if (!columnsByTable.has(table)) columnsByTable.set(table, new Set());
      columnsByTable.get(table).add(String(row?.Column ?? ""));
    }
    return new Map([...columnsByTable].map(([table, columns]) => [table, columns.size]));
  }, [profileMapRows]);

  useEffect(() => {
    if (profileMapTableNames.length === 0) {
      setActiveProfileMapTable("");
    } else if (!profileMapTableNames.includes(activeProfileMapTable)) {
      setActiveProfileMapTable(profileMapTableNames[0]);
    }
  }, [profileMapTableNames, activeProfileMapTable]);

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

  const visibleProfileMapGroups = useMemo(() => {
    const query = columnSearch.trim().toLowerCase();
    if (!query) return profileMapGroups;
    return profileMapGroups.filter((group) =>
      String(group.column || "").toLowerCase().includes(query)
    );
  }, [profileMapGroups, columnSearch]);

  const canEditProfileMap =
    canDownloadProfileMap && profileMapRows.length > 0 && profileMapVersion > 0 && !savingProfileMapEdits;
  const hasUnsavedProfileMapEdits =
    Object.keys(profileMapDraftEdits).length > 0 ||
    profileMapNewRows.length > 0 ||
    profileMapRemovedRows.length > 0;

  function profileMapCellValue(row, col) {
    const key = profileMapRowKey(row);
    return profileMapDraftEdits[key]?.[col] ?? row?.[col] ?? "";
  }

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

  function handleRemoveNewRuleRow(tempKey) {
    setProfileMapNewRows((prev) => prev.filter((newRow) => newRow.tempKey !== tempKey));
  }

  function handleRemoveSavedRuleRow(row) {
    const rowKey = profileMapRowKey(row);

    setProfileMapRemovedRows((prev) =>
      prev.includes(rowKey) ? prev : [...prev, rowKey]
    );

    setProfileMapDraftEdits((prev) => {
      if (!(rowKey in prev)) return prev;
      const next = { ...prev };
      delete next[rowKey];
      return next;
    });
  }

  function handleCancelProfileMapEdits() {
    setProfileMapDraftEdits({});
    setProfileMapNewRows([]);
    setProfileMapRemovedRows([]);
  }

  async function handleSaveProfileMapEdits() {
    if (!hasUnsavedProfileMapEdits) {
      setProfileMapEditMode(false);
      return;
    }

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

  const expandKey = (column) => `${activeProfileMapTable}::${column}`;

  const handleToggleExpand = (key) => {
    setExpandedColumns(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

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
        </div>
      </section>
    );
  }

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
             {savingProfileMapEdits ? (
               <>
                 <span className="metadata-spinner" aria-hidden="true" style={{ width: "14px", height: "14px" }} />{" "}
                 Saving…
               </>
             ) : (
               "Save Profile Map"
             )}
           </button>

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
