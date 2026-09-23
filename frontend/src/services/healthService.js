import { healthCheck } from "../api/api.js";

export async function checkHealth() {
  const { ok } = await healthCheck();
  return ok;
}

export default { checkHealth };
