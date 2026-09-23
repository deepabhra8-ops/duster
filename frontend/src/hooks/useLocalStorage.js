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

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
    }
  }, [key, value]);

  useEffect(() => {
    function onStorage(e) {
      if (e.key !== key) return;
      try {
        setValue(e.newValue === null ? initialValue : JSON.parse(e.newValue));
      } catch {
      }
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [key]);

  const remove = useCallback(() => {
    try {
      window.localStorage.removeItem(key);
    } catch {
    }
    setValue(typeof initialValue === "function" ? initialValue() : initialValue);
  }, [key, initialValue]);

  return [value, setValue, remove];
}

export default useLocalStorage;
