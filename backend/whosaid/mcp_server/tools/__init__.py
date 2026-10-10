"""One module per tool. Each is a plain function over the store: no MCP, no policy.

Tools are deliberately dumb: they do what they are told. Whether a call is *allowed* is
decided in front of them (by AgntID when enforcement is on), never inside them.
"""
