# ──────────────────────────────────────────────────────────────────────────────
#  Template for credentials. Copy this file to config.py and fill in your values.
#  config.py is gitignored — config.example.py is safe to commit.
# ──────────────────────────────────────────────────────────────────────────────

# Gmail credentials.
# Use a Google App Password, NOT your regular account password.
# Generate one at: myaccount.google.com/apppasswords
GMAIL_FROM     = "you@gmail.com"
GMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # 16-character App Password

# The recipient phone number is entered per-request in the web UI (or prompted
# interactively by the CLI). It is no longer a config-level constant.
