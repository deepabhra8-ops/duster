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

export default function RuleEditModal({
  isOpen,
  onClose,
  row,
  currentParams,
  currentNotes,
  onSave,
}) {
  const [params, setParams] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (isOpen) {
      setParams(currentParams || "");
      setNotes(currentNotes || "");
    }
  }, [isOpen, currentParams, currentNotes]);

  useScrollLock(isOpen);

  if (!isOpen || !row) return null;

  const ruleId = row[PROFILE_MAP_RULES_COLUMN];
  const column = row["Column"];
  const dataType = row["Data Type"];
  const ruleObj = DQ_RULES.find((r) => r.id === ruleId);
  const ruleName = ruleObj?.name || ruleObj?.cat || ruleId;

  const handleSave = () => {
    onSave({
      [PROFILE_MAP_PARAMS_COLUMN]: params,
      [PROFILE_MAP_NOTES_COLUMN]: notes,
    });
  };

  return (
    <ModalPortal>
      <div className="profile-map-modal-overlay">
        <div className="profile-map-modal">
          <div className="profile-map-modal-header">
            <h3>Edit Rule</h3>
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
                    {column} ({dataType})
                  </div>
                </div>
                <div className="form-group">
                  <label>Rule Type</label>
                  <div className="form-text-value rule-type-badge">
                    {ruleId} - {ruleName}
                  </div>
                </div>
              
                <div className="form-group">
                  <label>Parameters</label>
                  <input
                    type="text"
                    className="profile-map-cell-input"
                    value={params}
                    onChange={(e) => setParams(e.target.value)}
                    placeholder={ruleParameterHint(ruleId)}
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
              </div>

              <div className="profile-map-modal-right">
                <div className="rule-info-box">
                  <h4>{ruleName}</h4>
                  <p>{ruleDescription(ruleId)}</p>
                  {ruleParameterHint(ruleId) && (
                    <>
                      <h5>Supported parameters:</h5>
                      <p className="rule-hint-text">{ruleParameterHint(ruleId)}</p>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className="profile-map-modal-footer">
            <button className="btn btn-ghost" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={handleSave}>
              Save Rule
            </button>
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
