/**
 * A labeled connection-detail field (text/password input or a select), matching the
 * per-connector form mockups' `.field-label`/`.field-input` classes. `options` renders a
 * select instead of an input.
 */
export function FormField({ id, name, label, type = "text", defaultValue, options }) {
  return (
    <div>
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {options ? (
        <select id={id} name={name || id} className="field-input field-select" defaultValue={defaultValue}>
          {options.map((opt) => (
            <option key={opt}>{opt}</option>
          ))}
        </select>
      ) : (
        <input id={id} name={name || id} type={type} defaultValue={defaultValue} className="field-input" />
      )}
    </div>
  );
}

export default FormField;
