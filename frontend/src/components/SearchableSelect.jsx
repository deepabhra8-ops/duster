/**
 * SearchableSelect.jsx - generic type-to-filter, single-select dropdown.
 *
 * Presentational only: { value, options: [{ value, label }], onChange,
 * placeholder }. Built for ProfileMapper's "Select Saved Connection" field
 * (NewProfileMapperJobModal.jsx) - first real consumer of the
 * .metadata-select/.metadata-combobox/.metadata-dropdown/.metadata-option
 * CSS in global.css, which existed unused until now. Generic enough to
 * reuse anywhere else a searchable dropdown is needed later.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { ChevronDown } from "lucide-react";

export default function SearchableSelect({
  value,
  options,
  onChange,
  placeholder = "Search…",
  emptyLabel = "No matches",
  disabled = false,
  loading = false,
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef(null);

  const selected = options.find((o) => o.value === value) || null;

  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => o.label.toLowerCase().includes(q));
  }, [options, query]);

  function pick(opt) {
    onChange(opt.value);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="metadata-select" ref={rootRef}>
      <div className={`metadata-combobox${loading ? " is-loading" : ""}`}>
        <input
          type="text"
          placeholder={loading ? "Loading…" : placeholder}
          value={open ? query : selected?.label || ""}
          disabled={disabled || loading}
          aria-busy={loading || undefined}
          onFocus={() => {
            if (disabled) return;
            setOpen(true);
            setQuery("");
          }}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
        {loading ? (
          <span className="metadata-spinner" aria-hidden="true" />
        ) : (
          /* lucide, not the "⌄" character it used to render: that glyph sits
             high in its line box and varies with the installed font, so it read
             as a stray caret rather than a select's chevron. */
          <ChevronDown className="metadata-chevron" size={16} aria-hidden="true" />
        )}
      </div>

      {open ? (
        <div className="metadata-dropdown">
          {loading ? (
            <div className="metadata-option metadata-loading" aria-live="polite">
              <span className="metadata-spinner" aria-hidden="true" />
              Loading…
            </div>
          ) : filtered.length === 0 ? (
            <div className="metadata-option metadata-empty">{emptyLabel}</div>
          ) : (
            filtered.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`metadata-option${opt.value === value ? " selected" : ""}`}
                onClick={() => pick(opt)}
              >
                {opt.label}
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
