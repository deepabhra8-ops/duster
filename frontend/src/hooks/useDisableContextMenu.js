import { useEffect } from "react";

const ALLOW_IN_FIELDS = true;

const EDITABLE = new Set(["INPUT", "TEXTAREA"]);

function isEditable(target) {
  if (!target || !target.tagName) return false;
  if (EDITABLE.has(target.tagName)) return true;
  return typeof target.closest === "function" && Boolean(target.closest('[contenteditable="true"]'));
}

function isBlockedShortcut(event) {
  const key = String(event.key || "").toLowerCase();

  if (key === "f12") return true;

  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && key === "u") return true;

  if ((event.ctrlKey || event.metaKey) && event.shiftKey && ["i", "j", "c"].includes(key)) {
    return true;
  }

  return false;
}

export function useDisableContextMenu(enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined;

    function onContextMenu(event) {
      if (ALLOW_IN_FIELDS && isEditable(event.target)) return;
      event.preventDefault();
    }

    function onKeyDown(event) {
      if (!isBlockedShortcut(event)) return;
      event.preventDefault();
      event.stopPropagation();
    }

    document.addEventListener("contextmenu", onContextMenu, true);
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("contextmenu", onContextMenu, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [enabled]);
}

export default useDisableContextMenu;
