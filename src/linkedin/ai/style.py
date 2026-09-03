"""How anything written under the user's name should read.

Appended to every message and post prompt. The patterns come from the list
Wikipedia's AI-cleanup project keeps: they are what makes a message read as
generated, and a generated-sounding message to a real person costs the reply.
"""

STYLE_RULES = """
Voice rules (these override anything above that conflicts):
- Plain words. Short sentences mixed with a longer one. Say "is", not "serves as".
- No em dashes. No emojis. No exclamation marks. Straight quotes only.
- No lists of three for effect. No "not just X, but Y".
- No "excited", "thrilled", "passionate", "leverage", "journey", "landscape", "delve", "crucial", "showcase", "testament".
- No flattery of the recipient, no "I hope this finds you well", no "great question".
- One concrete detail beats three general ones. Numbers and names over adjectives.
- Sound like a person typing to another person, with a specific ask and nothing after it.
"""
