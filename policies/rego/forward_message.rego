package agntid.tools.whosaid.forward_message

default allow = false

# Forwarding needs a sender the user knows (contact, group admin or verified business) ...
write_trust = {"known_contact", "group_admin", "verified_business"}

# ... may only go to one of the user's existing contacts. allowed_recipients is a comma-separated list
# injected by WhoSaid (never by the model) ...
recipients = split(input.tool.inputs.allowed_recipients, ",")

allow {
    write_trust[input.tool.inputs.sender_trust]
    recipients[_] == input.tool.inputs.to
    not otp_like
}

# ... and must never carry an OTP or verification code.
otp_like {
    regex.match(`(?i)\b\d{4,8}\b|\botp\b|verification code|one[- ]time`, input.tool.inputs.content)
}
