import { BUTTON_REGISTERS, BUTTON_SIZES } from "./Button.variants.js";

export function Button({ register = "secondary", size = "default", className = "", children, ...rest }) {
  const classes = ["btn", BUTTON_REGISTERS[register], BUTTON_SIZES[size], className]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={classes} {...rest}>
      {children}
    </button>
  );
}

export default Button;
