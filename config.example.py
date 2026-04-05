# ──────────────────────────────────────────────────────────────────────────────
#  Template for credentials. Copy this file to config.py and fill in your values.
#  config.py is gitignored — config.example.py is safe to commit.
# ──────────────────────────────────────────────────────────────────────────────

# Gmail credentials.
# Use a Google App Password, NOT your regular account password.
# Generate one at: myaccount.google.com/apppasswords
GMAIL_FROM     = "you@gmail.com"
GMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # 16-character App Password

# T-Mobile email-to-SMS gateway: <10-digit number>@tmomail.net
# Other carriers: AT&T → @txt.att.net  |  Verizon → @vtext.com
SMS_TO = "2125551234@tmomail.net"
