/**
 * useDisableContextMenu.js - suppress the browser context menu and the
 * devtools/view-source keyboard shortcuts, app-wide.
 *
 * Mounted once, at the app root, so it covers every page including the login
 * screen - a listener on `document` in the capture phase catches the event
 * before any component can act on it, and there is nothing per-page to remember
 * to add.
 *
 * Worth being clear about what this is: it is a deterrent, not a control.
 * Preventing the keydown stops the SHORTCUT, not devtools - every browser also
 * opens them from its own menu (⋮ → More tools → Developer tools), which a page
 * cannot intercept, and the same is true of View Source and of opening the URL
 * in any other client. A browser may also decline to give the page the event at
 * all: F12 and Ctrl+Shift+I are reserved in some builds and configurations, so
 * the handler below is best-effort by nature and must never be relied on. It
 * raises the effort of a casual look; it does not stop anyone who intends to
 * look. Treating it as protection would be the mistake - the data that matters
 * is protected on the server, by authentication and by the credentials never
 * leaving it in plaintext.
 *
 * ALLOW_IN_FIELDS is the one carve-out, and it is a usability one rather than a
 * concession: inside a text input the context menu is how people cut, paste,
 * undo and reach spell-check suggestions. Blocking it there mostly punishes
 * someone filling in a connection form, not anyone inspecting the app. Set it
 * to false for a blanket block if that is what is wanted.
 */
import { useEffect } from "react";

/** Elements where the context menu stays available - see the header. */
const ALLOW_IN_FIELDS = true;

const EDITABLE = new Set(["INPUT", "TEXTAREA"]);

function isEditable(target) {
  if (!target || !target.tagName) return false;
  if (EDITABLE.has(target.tagName)) return true;
  // contenteditable regions, wherever they are nested.
  return typeof target.closest === "function" && Boolean(target.closest('[contenteditable="true"]'));
}

/**
 * The devtools and view-source shortcuts, as the browser reports them.
 *
 * Ctrl+Shift+J (console) and Ctrl+Shift+C (element picker) are included
 * alongside the three named: they open the same panel by another door, and
 * blocking only F12 would be theatre.
 *
 * `event.key` rather than `keyCode`: keyCode is deprecated and reports the
 * physical key, so it misreads on non-US layouts. The comparison is
 * case-insensitive because Shift makes `key` uppercase.
 */
function isBlockedShortcut(event) {
  const key = String(event.key || "").toLowerCase();

  // F12 - devtools, no modifier.
  if (key === "f12") return true;

  // Ctrl/Cmd + U - view source.
  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && key === "u") return true;

  // Ctrl/Cmd + Shift + I / J / C - devtools, console, element picker.
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
      // Stop it reaching any other handler as well - several of these are also
      // meaningful to the page (Ctrl+Shift+C, for instance).
      event.stopPropagation();
    }

    // Capture phase: these fire before any component-level handler, so the
    // block cannot be defeated by a stray listener stopping propagation.
    document.addEventListener("contextmenu", onContextMenu, true);
    document.addEventListener("keydown", onKeyDown, true);

    return () => {
      document.removeEventListener("contextmenu", onContextMenu, true);
      document.removeEventListener("keydown", onKeyDown, true);
    };
  }, [enabled]);
}

export default useDisableContextMenu;
