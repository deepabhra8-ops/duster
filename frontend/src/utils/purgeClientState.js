import { STORAGE_KEYS } from "../constants/appConfig.js";
import { clearAll } from "./pageCache.js";

export function purgeClientState() {
  clearAll();

  try {
    Object.values(STORAGE_KEYS).forEach((key) => window.localStorage.removeItem(key));
  } catch {
  }
}

export default purgeClientState;
