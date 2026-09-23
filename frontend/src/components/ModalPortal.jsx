import { createPortal } from "react-dom";

export default function ModalPortal({ children }) {
  if (typeof document === "undefined") return children;

  return createPortal(children, document.body);
}
