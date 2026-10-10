# Per-tool input constraints (PROVISIONAL)

Written before the AgntID docs were available; the exact field names and syntax of the portal's
input-constraint editor are to be filled in during phase c. The intent is what matters.

Constraints that can be expressed on one tool's arguments alone (no cross-argument logic):

| Tool | Argument | Constraint |
|---|---|---|
| `pay_upi` | `amount_inr` | number, `0 < amount_inr <= 10000` |
| `pay_upi` | `payee_upi` | string matching `^[\w.\-]{2,}@[a-z]{2,}$` |
| `forward_message` | `content` | must not match `(?i)\b\d{4,8}\b\|\botp\b\|verification code\|one[- ]time` |
| `read_otp_messages` | *(tool)* | block entirely |
| `forward_message` | `to` | must be one of `allowed_recipients` (cross-argument: see Rego) |
| `update_preferences` | *(tool)* | deny whenever `message_id` is non-empty, i.e. always for an agent (see Rego) |
| `update_preferences` | `key` | enum: `never_mute_sender`, `never_mute_group`, `never_mute_business`, `mute_promotions`, `dnd_window`, `auto_pay_sender` |
| every tool | `sender_trust` | enum: `unknown`, `known_contact`, `group_admin`, `verified_business` |

Cross-argument rules (these need Rego, see `whosaid.rego`):

* `pay_upi.payee_upi` must equal `registered_payee`
* write actions require `sender_trust != unknown`
* `forward_message.to` must be in `allowed_recipients` (the user's existing contacts, injected by WhoSaid)
* `pay_upi` requires `sender_trust` in `group_admin`, `verified_business`
