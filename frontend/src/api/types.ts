import type {
  Dataset, Enforcement, Preferences, RunComparison, RunDetail, RunEvent, RunHandle,
} from "../types";

export interface WhoSaidApi {
  /** true when serving built-in fixtures; the UI shows a "demo data" marker. */
  readonly mock: boolean;
  listDatasets(): Promise<Dataset[]>;
  uploadDataset(files: File[]): Promise<Dataset>;
  /** The demo dataset ships with the backend; real mode picks it from GET /datasets. */
  useDemoDataset(): Promise<Dataset>;
  startRun(datasetId: string, enforcement: Enforcement): Promise<RunHandle>;
  /** Subscribe to progress events. Returns an unsubscribe function. */
  streamEvents(runId: string, onEvent: (e: RunEvent) => void, onError: (err: Error) => void): () => void;
  getRun(runId: string): Promise<RunDetail>;
  compareRuns(offRunId: string, onRunId: string): Promise<RunComparison>;
  reset(): Promise<void>;
  getPreferences(userId: string): Promise<Preferences>;
  putPreferences(userId: string, prefs: Preferences): Promise<Preferences>;
}
