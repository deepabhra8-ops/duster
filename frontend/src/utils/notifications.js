export function isInternalPath(link) {
  return (
    typeof link === "string" &&
    link.startsWith("/") &&
    !link.startsWith("//") &&
    !link.includes("\\") &&
    !/[\u0000-\u001f\u007f]/.test(link)
  );
}

const TONE_BY_TYPE = {
  job_done: "success",
  job_error: "error",
  job_cancelled: "warn",
  success: "success",
  error: "error",
  warning: "warn",
  info: "info",
};

export const notificationTone = (type) => TONE_BY_TYPE[type] || "info";
