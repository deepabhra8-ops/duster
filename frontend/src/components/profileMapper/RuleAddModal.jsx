import React, { useState, useEffect } from "react";
import { useScrollLock } from "../../hooks/useScrollLock.js";
import { DQ_RULES } from "../../constants/dqRules.js";
import ModalPortal from "../ModalPortal.jsx";

const PROFILE_MAP_RULES_COLUMN = "Applicable Rules";
const PROFILE_MAP_PARAMS_COLUMN = "Rule Parameters";
const PROFILE_MAP_NOTES_COLUMN = "Analyst Notes";
const NOTES_MAX_LENGTH = 200;

const ruleParameterHint = (ruleId) =>
  (DQ_RULES.find((rule) => rule.id === ruleId)?.params || "").trim();

const ruleDescription = (ruleId) =>
  (DQ_RULES.find((rule) => rule.id === ruleId)?.desc || "").trim();

export default function RuleAddModal({
  isOpen,
  onClose,
  columnName,
  dataType,
  takenRules,
  onAdd,
}) {
  const [selectedRuleId, setSelectedRuleId] = useState("");
  const [params, setParams] = useState("");
  const [notes, setNotes] = useState("");
  const [duplicateWarning, setDuplicateWarning] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setSelectedRuleId("");
      setParams("");
      setNotes("");
      setDuplicateWarning(false);
    }
  }, [isOpen]);

  useScrollLock(isOpen);

  if (!isOpen) return null;

  const handleRuleSelect = (e) => {
    const newRuleId = e.target.value;
    if (takenRules.has(newRuleId)) {
      setDuplicateWarning(true);
      setSelectedRuleId("");
    } else {
      setDuplicateWarning(false);
      setSelectedRuleId(newRuleId);
      setParams("");
    }
  };

  const handleAdd = () => {
    if (!selectedRuleId) return;
    
    onAdd({
      [PROFILE_MAP_RULES_COLUMN]: selectedRuleId,
      [PROFILE_MAP_PARAMS_COLUMN]: params,
      [PROFILE_MAP_NOTES_COLUMN]: notes,
    });
  };

  const ruleObj = DQ_RULES.find((r) => r.id === selectedRuleId);
  const ruleName = ruleObj?.name || ruleObj?.cat || selectedRuleId;

  return (
    <ModalPortal>
      <div className="profile-map-modal-overlay">
        <div className="profile-map-modal">
          <div className="profile-map-modal-header">
            <h3>Add Rule to {columnName}</h3>
            <button className="profile-map-modal-close" onClick={onClose} aria-label="Close">
              <span style={{ "--icon-src": "url(/icons/close.svg)" }} className="icon-span" />
            </button>
          </div>
          <div className="profile-map-modal-body">
            <div className="profile-map-modal-split">
              <div className="profile-map-modal-left">
                <div className="form-group">
                  <label>Column</label>
                  <div className="form-text-value">
                    {columnName} ({dataType})
                  </div>
                </div>
              
                <div className="form-group">
                  <label>Rule Type</label>
                  <select
                    className="profile-map-cell-input rule-select"
                    value={selectedRuleId}
                    onChange={handleRuleSelect}
                  >
                    <option value="" disabled>Select a rule type</option>
                    {DQ_RULES.map((rule) => {
                      const isTaken = takenRules.has(rule.id);
                      return (
                        <option 
                          key={rule.id} 
                          value={rule.id} 
                          disabled={isTaken}
                        >
                          {rule.id} - {rule.cat} {isTaken ? "(Added)" : ""}
                        </option>
                      );
                    })}
                  </select>
                </div>
              
                {selectedRuleId && (
                  <>
                    <div className="form-group">
                      <label>Parameters</label>
                      <input
                        type="text"
                        className="profile-map-cell-input"
                        value={params}
                        onChange={(e) => setParams(e.target.value)}
                        placeholder={ruleParameterHint(selectedRuleId)}
                      />
                    </div>

                    <div className="form-group">
                      <label>Analyst Notes</label>
                      <textarea
                        className="profile-map-cell-input"
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="Add notes (optional)"
                        rows={3}
                        maxLength={NOTES_MAX_LENGTH}
                      />
                      <span className="hint" style={{ display: "block", textAlign: "right" }}>
                        {notes.length}/{NOTES_MAX_LENGTH}
                      </span>
                    </div>

                    <div className="form-group">
                      <label>Enabled</label>
                      <div className="toggle-switch read-only">
                        <input type="checkbox" checked={true} readOnly />
                        <span className="slider round"></span>
                      </div>
                    </div>
                  </>
                )}

              </div>

              <div className="profile-map-modal-right">
                 {duplicateWarning ? (
                    <div className="alert alert-warn rule-warning">
                      <h4>This rule is already added for this column</h4>
                      <p>You cannot add duplicate rule types for the same column.</p>
                    </div>
                 ) : selectedRuleId ? (
                  <div className="rule-info-box">
                    <h4>{ruleName}</h4>
                    <p>{ruleDescription(selectedRuleId)}</p>
                    {ruleParameterHint(selectedRuleId) && (
                      <>
                        <h5>Supported parameters:</h5>
                        <p className="rule-hint-text">{ruleParameterHint(selectedRuleId)}</p>
                      </>
                    )}
                  </div>
                ) : (
                  <div className="rule-info-box empty">
                    <p>Select a rule type to see details.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="profile-map-modal-footer">
            <button className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button 
              className="btn btn-primary" 
              onClick={handleAdd}
              disabled={!selectedRuleId || duplicateWarning}
            >
              Add Rule
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
