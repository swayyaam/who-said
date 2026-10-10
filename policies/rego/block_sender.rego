package agntid.tools.whosaid.block_sender

default allow = false

# Blocking is a protective action, so it is open to every sender, but only for a valid trust level.
known_trust = {"unknown", "known_contact", "group_admin", "verified_business"}

allow {
    known_trust[input.tool.inputs.sender_trust]
}
