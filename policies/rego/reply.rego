package agntid.tools.whosaid.reply

default allow = false

# Replying needs a sender the user knows: a contact, a group admin or a verified business.
write_trust = {"known_contact", "group_admin", "verified_business"}

allow {
    write_trust[input.tool.inputs.sender_trust]
}
