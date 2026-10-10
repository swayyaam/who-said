package agntid.tools.whosaid.pay_upi

default allow = false

# Who may lead to a payment: a group admin or a verified business (the trust level is computed in code).
payment_trust = {"group_admin", "verified_business"}

# INR this user has already paid THIS payee, from the ledger. A decimal string injected by WhoSaid, never by the
# model (the AgntID runtime types every parameter as a string). If it is missing the rule is undefined: deny.
paid = to_number(input.tool.inputs.paid_today_to_payee)

allow {
    payment_trust[input.tool.inputs.sender_trust]
    input.tool.inputs.registered_payee != ""
    input.tool.inputs.payee_upi == input.tool.inputs.registered_payee
    input.tool.inputs.amount_inr > 0
    input.tool.inputs.amount_inr <= 10000
    # The limit is cumulative per payee, so splitting a payment into small ones cannot get around it.
    input.tool.inputs.amount_inr + paid <= 10000
}
