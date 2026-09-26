import { Search } from "lucide-react";

/**
 * The category-chip + search row above a filterable grid (e.g. Connections). `categories` is
 * a plain string list; "All" is added automatically as the first chip.
 */
export function CategoryToolbar({ categories, active, onSelect, search, onSearchChange, searchPlaceholder }) {
  return (
    <div className="category-toolbar">
      <div className="cat-row">
        <button type="button" className={`cat-chip${active === "All" ? " is-active" : ""}`} onClick={() => onSelect("All")}>
          All
        </button>
        {categories.map((category) => (
          <button
            key={category}
            type="button"
            className={`cat-chip${active === category ? " is-active" : ""}`}
            onClick={() => onSelect(category)}
          >
            {category}
          </button>
        ))}
      </div>
      <div className="page-search">
        <Search aria-hidden="true" />
        <input
          type="text"
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
    </div>
  );
}

export default CategoryToolbar;
