/**
 * Thin wrapper around the design system's static icon assets in /public/icons/*.svg.
 * Rendered via a plain <img> per the artifact's Icons note — these are shape references
 * (monochrome outline SVGs), not currentColor-aware inline icons.
 */
export function Icon({ name, size = 16, alt = "", className = "" }) {
  return (
    <img
      src={`/icons/${name}.svg`}
      width={size}
      height={size}
      alt={alt}
      aria-hidden={alt ? undefined : "true"}
      className={className}
    />
  );
}

export default Icon;
