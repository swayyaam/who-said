import { HugeiconsIcon } from "@hugeicons/react";
import {
  Calendar01Icon, CreditCardIcon, Forward01Icon, Key01Icon, Message01Icon, Settings01Icon, UserBlock01Icon,
} from "@hugeicons/core-free-icons";
import type { ToolAttempt } from "../types";
import { keyArg } from "../lib/trace";
import CallChip, { type CallStatus } from "./CallChip";

const ICON = {
  pay_upi: CreditCardIcon,
  forward_message: Forward01Icon,
  reply: Message01Icon,
  create_calendar_event: Calendar01Icon,
  block_sender: UserBlock01Icon,
  update_preferences: Settings01Icon,
  read_otp_messages: Key01Icon,
} as const;

/** A tool call as a chip: name, the key argument, and (once decided) AgntID's verdict. */
export function ToolChip({ attempt, status, showTimer = false, expectedMs = 400, size = 30 }: {
  attempt: ToolAttempt; status: CallStatus; showTimer?: boolean; expectedMs?: number; size?: number;
}) {
  const icon = ICON[attempt.call.tool as keyof typeof ICON];
  return (
    <CallChip
      name={attempt.call.tool}
      argument={keyArg(attempt.call)}
      status={status}
      showTimer={showTimer}
      expectedMs={expectedMs}
      size={size}
      radius={8}
      icon={icon ? <HugeiconsIcon icon={icon} size={Math.max(11, Math.round(size * 0.38)) + 2} strokeWidth={1.8} /> : null}
    />
  );
}

/** Final status of a call from AgntID's decision (static chips). */
export const finalStatus = (a: ToolAttempt): CallStatus => (a.decision.allowed ? "done" : "error");
