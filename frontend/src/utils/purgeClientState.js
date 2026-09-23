/**
 * purgeClientState.js - forget everything this browser holds about the session.
 *
 * Called on sign-out AND on a 401, since a session that expires server-side
 * never runs through logout().
 *
 * Two things are cleared:
 *
 *  1. The page cache (sessionStorage, `dqc:` keys). Job names, connection names
 *     and dashboard figures are per-user data and must not survive into the next
 *     person's session on a shared machine.
 *
 *  2. A pre-existing leak in localStorage. `dq_current_job_meta` and
 *     `dq_latest_results` hold entire job payloads - summary, log, job data -
 *     and `dq_user_config` holds a config object whose shape includes
 *     connectionDetails/connection_string. Nothing has ever removed these, so
 *     they outlived sign-out. Two of them are written with raw
 *     localStorage.setItem rather than through useLocalStorage, so a
 *     hook-based cleanup would miss them; they are enumerated explicitly here.
 */
import { STORAGE_KEYS } from "../constants/appConfig.js";
import { clearAll } from "./pageCache.js";

export function purgeClientState() {
  clearAll();

  try {
    Object.values(STORAGE_KEYS).forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // Storage can be unavailable or read-only; a failed purge must not block
    // the sign-out itself.
  }
}

export default purgeClientState;
