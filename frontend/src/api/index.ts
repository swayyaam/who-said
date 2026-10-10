import { mockApi } from "./mock";
import { realApi } from "./client";
import type { WhoSaidApi } from "./types";

// The one-line switch: VITE_USE_MOCK=false (in .env.local) talks to VITE_API_URL.
const useMock = (import.meta.env.VITE_USE_MOCK ?? "true") !== "false";
export const api: WhoSaidApi = useMock ? mockApi : realApi;
export type { WhoSaidApi };
