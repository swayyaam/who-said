# PROVISIONAL DRAFT -- written before the AgntID docs were available.
#
# This expresses the WhoSaid permission policy in plain OPA Rego. The package name, the shape
# of `input`, and the way a deny reason is returned are ASSUMPTIONS to be aligned with the
# AgntID docs (custom Rego rules) in phase c. The logic is the part that matters, and it is
# tested: backend/tests/policy_oracle.py states the same rules in Python.
#
# Assumed input:
#   input.tool        tool name, e.g. "pay_upi"
#   input.arguments   the tool arguments, including the trusted ones injected by WhoSaid:
#                     sender_trust, registered_payee, allowed_recipients, user_id, message_id, sender_id
package whosaid.authz

import rego.v1

payment_limit_inr := 10000

write_tools := {"reply", "forward_message", "create_calendar_event", "pay_upi"}
contact_or_better := {"known_contact", "group_admin", "verified_business"}
payment_capable := {"group_admin", "verified_business"}

trust := object.get(input.arguments, "sender_trust", "unknown")

# ---- deny rules, each with a human-readable reason ------------------------------------

deny contains msg if {
	input.tool == "read_otp_messages"
	msg := "DENIED read_otp_messages: OTP and verification-code messages are never readable by the agent"
}

deny contains msg if {
	input.tool == "forward_message"
	regex.match(`(?i)\b\d{4,8}\b|\botp\b|verification code|one[- ]time`, object.get(input.arguments, "content", ""))
	msg := "DENIED forward_message: content looks like an OTP or verification code"
}

deny contains msg if {
	input.tool == "forward_message"
	trust in contact_or_better
	not input.arguments.to in object.get(input.arguments, "allowed_recipients", [])
	msg := sprintf("DENIED forward_message: %s is not one of the user's existing contacts", [input.arguments.to])
}

deny contains msg if {
	input.tool in write_tools
	not trust in contact_or_better
	msg := sprintf("DENIED %s: sender %s, write actions not permitted", [input.tool, trust])
}

deny contains msg if {
	input.tool == "pay_upi"
	trust in contact_or_better
	not trust in payment_capable
	msg := sprintf("DENIED pay_upi: sender %s is not a group admin or verified business", [trust])
}

deny contains msg if {
	input.tool == "pay_upi"
	trust in payment_capable
	object.get(input.arguments, "registered_payee", "") == ""
	msg := "DENIED pay_upi: sender has no registered payee or existing relationship"
}

deny contains msg if {
	input.tool == "pay_upi"
	trust in payment_capable
	registered := object.get(input.arguments, "registered_payee", "")
	registered != ""
	input.arguments.payee_upi != registered
	msg := sprintf("DENIED pay_upi: payee %s does not match the sender's registered payee", [input.arguments.payee_upi])
}

deny contains msg if {
	input.tool == "pay_upi"
	trust in payment_capable
	input.arguments.amount_inr > payment_limit_inr
	msg := sprintf("DENIED pay_upi: amount exceeds the limit of %d INR", [payment_limit_inr])
}

# ---- decision ---------------------------------------------------------------------------

default allow := false

allow if count(deny) == 0
