import React from "react";
import { ChevronRight, MoreVertical, Pencil, Trash2, Plus } from "lucide-react";
import { DQ_RULES } from "../../constants/dqRules.js";

const PROFILE_MAP_RULES_COLUMN = "Applicable Rules";
const PROFILE_MAP_PARAMS_COLUMN = "Rule Parameters";
const PROFILE_MAP_NOTES_COLUMN = "Analyst Notes";
const PROFILE_MAP_ENABLED_COLUMN = "Enabled";
const PROFILE_MAP_CDE_COLUMN = "CDE (X=Yes)";

export default function ExpandableColumnRow({
  groupIndex,
  group,
  lines,
  isExpanded,
  onToggleExpand,
  profileMapDraftEdits,
  profileMapRowKey,
  handleProfileMapColumnLevelChange,
  isProfileMapCheckboxChecked,
  onEditRule,
  onAddRule,
  onDeleteSavedRule,
  onDeleteNewRule,
  profileMapRemovedRows,
}) {
  const headRow = group.rows[0];

  const getCellValue = (row, col) => {
    const key = profileMapRowKey(row);
    return profileMapDraftEdits[key]?.[col] ?? row?.[col] ?? "";
  };

  const isColEdited = (col) => {
    return group.rows.some(
      (row) => profileMapDraftEdits[profileMapRowKey(row)]?.[col] !== undefined
    );
  };

  const survivingRules = lines.filter((line) => {
    if (line.kind === "saved") {
       return !profileMapRemovedRows.includes(line.key);
    }
    return line.kind === "pending";
  }).length;

  return (
    <>
      <tr className="profile-map-parent-row">
        <td className="expand-cell" onClick={onToggleExpand} style={{ cursor: "pointer", color: "#718096" }}>
           <ChevronRight
              size={16}
              className={`expand-icon-lucide ${isExpanded ? "expanded" : ""}`}
              style={{
                transition: "transform 0.2s ease",
                transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)"
              }}
              aria-hidden="true"
           />
        </td>
        <td className="profile-map-row-num">{groupIndex + 1}</td>
        
        <td className={`profile-map-editable-cell ${isColEdited(PROFILE_MAP_ENABLED_COLUMN) ? "is-edited" : ""}`}>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={survivingRules > 0}
              onChange={(e) => handleProfileMapColumnLevelChange(group, PROFILE_MAP_ENABLED_COLUMN, e.target.checked)}
              aria-label={`Enabled for ${group.column}`}
            />
            <span className="slider round"></span>
          </label>
        </td>

        <td>{headRow["Column"] || "-"}</td>
        <td>{headRow["Data Type"] || "-"}</td>
        <td>{headRow["Total Count"] || "-"}</td>
        <td>{headRow["Null Count"] || "-"}</td>
        <td>{headRow["Null %"] || "-"}</td>
        <td>{headRow["Distinct Count"] || "-"}</td>
        <td>{headRow["Unique %"] || "-"}</td>
        <td>{headRow["Min Value"] || "-"}</td>
        <td>{headRow["Max Value"] || "-"}</td>
        
        <td>
          <button className="rules-badge" onClick={onToggleExpand}>
            {survivingRules} rule{survivingRules !== 1 ? 's' : ''}
          </button>
        </td>

        <td className={`profile-map-editable-cell ${isColEdited(PROFILE_MAP_CDE_COLUMN) ? "is-edited" : ""}`}>
           <input
              type="checkbox"
              className="cde-checkbox"
              checked={isProfileMapCheckboxChecked(getCellValue(headRow, PROFILE_MAP_CDE_COLUMN), PROFILE_MAP_CDE_COLUMN)}
              onChange={(e) => handleProfileMapColumnLevelChange(group, PROFILE_MAP_CDE_COLUMN, e.target.checked)}
              aria-label={`CDE for ${group.column}`}
            />
        </td>

      </tr>

      {isExpanded && (
        <tr className="profile-map-child-row">
          <td colSpan={13}>
            <div className="rules-subtable-container">
              <div className="rules-subtable-header">
                 <h4>Rules for {group.column} ({survivingRules})</h4>
                 <button className="btn btn-secondary btn-sm" onClick={() => onAddRule(group)} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                   <Plus size={14} /> Add Rule
                 </button>
              </div>
              <table className="rules-subtable">
                <thead>
                  <tr>
                    <th>Rule ID</th>
                    <th>Rule Name</th>
                    <th>Category</th>
                    <th>Parameters</th>
                    <th>Analyst Notes</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line) => {
                    if (line.kind === "saved") {
                      if (profileMapRemovedRows.includes(line.key)) return null;
                      
                      const row = line.row;
                      const ruleId = row[PROFILE_MAP_RULES_COLUMN];
                      const ruleObj = DQ_RULES.find((r) => r.id === ruleId);
                      const ruleName = ruleObj?.name || ruleObj?.cat || ruleId;
                      const cat = ruleObj?.cat || "-";
                      const params = getCellValue(row, PROFILE_MAP_PARAMS_COLUMN);
                      const notes = getCellValue(row, PROFILE_MAP_NOTES_COLUMN);
                      
                      const isParamsEdited = profileMapDraftEdits[line.key]?.[PROFILE_MAP_PARAMS_COLUMN] !== undefined;
                      const isNotesEdited = profileMapDraftEdits[line.key]?.[PROFILE_MAP_NOTES_COLUMN] !== undefined;

                      return (
                        <tr key={line.key}>
                          <td>{ruleId}</td>
                          <td>{ruleName}</td>
                          <td>{cat}</td>
                          <td className={isParamsEdited ? "is-edited-text" : ""}>{params || "—"}</td>
                          <td className={isNotesEdited ? "is-edited-text" : ""}>{notes || "—"}</td>
                          <td>
                            <div className="status-badge enabled">
                               <span className="dot"></span> Enabled
                            </div>
                          </td>
                           <td className="actions-cell">
                             <button className="icon-btn edit-btn" onClick={() => onEditRule(line)} title="Edit Rule">
                               <Pencil size={16} />
                             </button>
                             <button className="icon-btn delete-btn" onClick={() => onDeleteSavedRule(row)} title="Delete Rule">
                               <Trash2 size={16} />
                             </button>
                           </td>
                        </tr>
                      );
                    }

                    if (line.kind === "pending") {
                      const { tempKey, values } = line.newRow;
                      const ruleId = values[PROFILE_MAP_RULES_COLUMN];
                      const ruleObj = DQ_RULES.find((r) => r.id === ruleId);
                      const ruleName = ruleObj?.name || ruleObj?.cat || ruleId;
                      const cat = ruleObj?.cat || "-";
                      
                      return (
                        <tr key={tempKey} className="is-new-row">
                          <td>{ruleId}</td>
                          <td>{ruleName}</td>
                          <td>{cat}</td>
                          <td className="is-edited-text">{values[PROFILE_MAP_PARAMS_COLUMN] || "—"}</td>
                          <td className="is-edited-text">{values[PROFILE_MAP_NOTES_COLUMN] || "—"}</td>
                          <td>
                            <div className="status-badge enabled">
                               <span className="dot"></span> Enabled
                            </div>
                          </td>
                           <td className="actions-cell">
                             <button className="icon-btn edit-btn" onClick={() => onEditRule(line)} title="Edit Rule">
                               <Pencil size={16} />
                             </button>
                             <button className="icon-btn delete-btn" onClick={() => onDeleteNewRule(tempKey)} title="Delete Rule">
                               <Trash2 size={16} />
                             </button>
                           </td>
                        </tr>
                      );
                    }
                    
                    return null;
                  })}
                  
                  {survivingRules === 0 && (
                     <tr>
                        <td colSpan={7} className="empty-rules">No rules applied to this column.</td>
                     </tr>
                  )}
                </tbody>
              </table>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
