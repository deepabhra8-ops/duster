import { Link } from "react-router-dom";
import { BUTTON_REGISTERS, BUTTON_SIZES } from "./Button.variants.js";

/** `to` renders the button as a router Link (styled identically) instead of a <button>. */
export function Button({ register = "secondary", size = "default", className = "", to, children, ...rest }) {
  const classes = ["btn", BUTTON_REGISTERS[register], BUTTON_SIZES[size], className]
    .filter(Boolean)
    .join(" ");

  if (to) {
    return (
      <Link to={to} className={classes} {...rest}>
        {children}
      </Link>
    );
  }

  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  );
}

export default Button;
