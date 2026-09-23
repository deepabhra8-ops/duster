/**
 * useLocalStorage.js - React state synced to localStorage.
 *
 * Drop-in replacement for the vanilla Store pattern: values are JSON
 * serialized, reads/writes are guarded with try/catch, and the hook
 * stays in sync across tabs via the native `storage` event.
 *
 * @param {string} key            localStorage key
 * @param {*}      initialValue   value (or lazy initializer) when nothing is stored
 * @returns {[value, setValue, removeValue]}
 *
 * Usage:
 *   const [page, setPage] = useLocalStorage("dq_active_page", "configure");
 */
import { useCallback, useEffect, useState } from "react";

function readStored(key, initialValue) {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return typeof initialValue === "function" ? initialValue() : initialValue;
    }
    return JSON.parse(raw);
  } catch {
    return typeof initialValue === "function" ? initialValue() : initialValue;
  }
}

export function useLocalStorage(key, initialValue) {
  const [value, setValue] = useState(() => readStored(key, initialValue));

  // Persist whenever the value changes.
  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage full or unavailable - ignore */
    }
  }, [key, value]);

  // Keep multiple tabs / components in sync.
  useEffect(() => {
    function onStorage(e) {
      if (e.key !== key) return;
      try {
        setValue(e.newValue === null ? initialValue : JSON.parse(e.newValue));
      } catch {
        /* ignore malformed payloads */
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
    // initialValue intentionally excluded - only key identity matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const remove = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
    setValue(typeof initialValue === "function" ? initialValue() : initialValue);
  }, [key, initialValue]);

  return [value, setValue, remove];
}

export default useLocalStorage;
