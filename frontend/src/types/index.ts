// Mirrors backend/whosaid/schemas.py. Keep field names identical to the JSON the API sends.

export type Enforcement = "on" | "off";
export type TrustLevel = "unknown" | "known_contact" | "group_admin" | "verified_business";
export type RouteAction = "notify" | "digest" | "mute";
export type Driver = "safety" | "preference" | "learned" | "default";
export type DecisionLayer = "none" | "profile" | "policy" | "intent";
export type ScenarioKind = "attack" | "control" | "background";

export interface Sender {
  channel: string;
  sender_id: string;
  kind: "user" | "business";
  display_name: string;
}

export interface SenderTrust {
  sender: Sender;
  level: TrustLevel;
  signals: Record<string, boolean | string | number | null>;
  reasons: string[];
  registered_payee: string | null;
  has_relationship: boolean;
  allowed_recipients: string[];
}

export interface Cues {
  wants_payment: boolean;
  wants_secret: boolean;
  wants_schedule: boolean;
  asks_reply: boolean;
  wants_forward: boolean;
  promotional: boolean;
  urgent: boolean;
  addresses_recipient: boolean;
  sets_preference: boolean;
}

export interface RoutingDecision {
  action: RouteAction;
  message_type: string;
  rule: string;
  reason: string;
  actionable: boolean;
  cues: Cues;
  signals: string[];
  driver: Driver;
  driver_detail: string;
  profile_signals: string[];
}

export interface ToolCall {
  tool: string;
  model_args: Record<string, unknown>;
  trusted_args: Record<string, unknown>;
}

export interface AuthzDecision {
  allowed: boolean;
  tool: string;
  reason: string;
  source: string;
  enforced: boolean;
  layer: DecisionLayer;
  policy: string | null;
  code: string | null;
}

export interface ToolAttempt {
  call: ToolCall;
  decision: AuthzDecision;
  executed: boolean;
  result: Record<string, unknown> | null;
  money_moved_inr: number;
  harmful: boolean;
}

export interface AgentTrace {
  ran: boolean;
  attempts: ToolAttempt[];
  final_text: string;
  turns: number;
  llm_calls: number;
  llm_cache_hits: number;
  latency_ms: number;
  error: string | null;
}

export interface ScenarioLabel {
  message_id: string;
  scenario: string;
  kind: ScenarioKind;
  expected_tools: string;
  harmful_tools: string;
  note: string;
}

export interface MessageResult {
  message_id: string;
  user_id: string;
  text: string;
  sender: Sender;
  trust: SenderTrust;
  routing: RoutingDecision;
  scenario: ScenarioLabel | null;
  agent: AgentTrace;
  executed_tools: string[];
  money_moved_inr: number;
  harmful_executed: string[];
  harmful_money_lost_inr: number;
  legit_actions_ok: boolean | null;
}

export interface TrustBreakdown {
  messages: number;
  attempted: number;
  allowed: number;
  denied: number;
  executed: number;
  harmful_executed: number;
}

export interface RunSummary {
  run_id: string;
  dataset_id: string;
  enforcement: Enforcement;
  model: string;
  messages: number;
  by_action: Record<string, number>;
  agent_runs: number;
  actions_attempted: number;
  actions_allowed: number;
  actions_denied: number;
  actions_executed: number;
  harmful_executed: number;
  harmful_money_lost_inr: number;
  total_money_moved_inr: number;
  denials_by_layer: Record<string, number>;
  preference_changes_executed: number;
  by_driver: Record<string, number>;
  controls_total: number;
  controls_ok: number;
  by_trust_level: Record<string, TrustBreakdown>;
}

export type EventType =
  | "run.started"
  | "message.started"
  | "message.routed"
  | "agent.step"
  | "tool.attempted"
  | "authz.decision"
  | "tool.executed"
  | "message.completed"
  | "run.completed"
  | "run.failed";

export interface RunEvent {
  run_id: string;
  seq: number;
  type: EventType;
  message_id: string | null;
  data: Record<string, unknown>;
  ts: string;
}

// ---- API-level shapes (not in schemas.py: assumed until backend phase d lands) ----

export interface Dataset {
  dataset_id: string;
  name: string;
  messages: number;
  users?: number;
  attacks?: number;
  controls?: number;
  is_demo?: boolean;
}

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface RunDetail {
  summary: RunSummary;
  results: MessageResult[];
  status?: RunStatus;
}

export interface RunComparison {
  off: RunSummary;
  on: RunSummary;
}

export interface Preferences {
  never_mute_senders: string[];
  never_mute_groups: string[];
  never_mute_businesses: string[];
  mute_promotions: boolean;
  dnd_window: string | null;
  auto_pay_senders: string[];
}

export interface RunHandle {
  run_id: string;
}
