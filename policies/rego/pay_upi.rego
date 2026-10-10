package agntid.tools.whosaid.pay_upi

default allow = false

# Who may lead to a payment: a group admin or a verified business (the trust level is computed in code).
payment_trust = {"group_admin", "verified_business"}

allow {
    payment_trust[input.tool.inputs.sender_trust]
    input.tool.inputs.registered_payee != ""
    input.tool.inputs.payee_upi == input.tool.inputs.registered_payee
    input.tool.inputs.amount_inr > 0
    input.tool.inputs.amount_inr <= 10000
}
