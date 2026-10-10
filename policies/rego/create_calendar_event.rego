package agntid.tools.whosaid.create_calendar_event

default allow = false

# Adding a calendar event needs a sender the user knows: a contact, a group admin or a verified business.
write_trust = {"known_contact", "group_admin", "verified_business"}

allow {
    write_trust[input.tool.inputs.sender_trust]
}
