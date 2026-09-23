/**
 * ProfileMapSection.jsx - Profile Map selector (Step 3 only).
 *
 * Lets the analyst pick a reviewed Source-DQ-Profile-Map.xlsx from the
 * uploaded mapping files, or leave blank to auto-generate from Step 1.
 * Visibility is controlled by the parent (rendered only when step === 3).
 */
export default function ProfileMapSection({ value, profileMaps = [], onChange }) {
  return (
    <div className="card" id="section-profile-map">
      <div className="card-title">
        🗺️ Profile Map <span className="badge">Step 3 only</span>
      </div>
      <p className="section-desc">
        Upload your analyst-reviewed <strong>Source-DQ-Profile-Map.xlsx</strong> for Step 3, or leave empty to
        auto-generate.
      </p>
      <div className="form-grid">
        <div className="form-group">
          <label htmlFor="cfg-profile-map">Profile Map File</label>
          <select id="cfg-profile-map" value={value || ""} onChange={(e) => onChange(e.target.value)}>
            <option value="">- Auto-generate from Step 1 -</option>
            {profileMaps.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
