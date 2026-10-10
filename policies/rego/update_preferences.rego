package agntid.tools.whosaid.update_preferences

default allow = false

# Preferences change only through the user's own API, never through a tool call. Every call an agent makes
# carries the id of the incoming message it is handling (injected by WhoSaid), so a call with a message id
# originates from a message and is denied. A call with no message id (undefined or empty) is the only allowed shape.
allow {
    input.tool.inputs.message_id == ""
}
