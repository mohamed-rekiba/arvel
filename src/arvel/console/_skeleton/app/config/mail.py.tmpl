"""Mail config — the default transport.

`log` (the default) records messages without sending — ideal for dev/tests. `smtp` sends via a real
aiosmtplib connection; fill in the host/credentials (and `encryption`: "tls" = STARTTLS, "ssl" =
implicit TLS, "" = none). Send via the `Mail` facade (`await Mail.to(user).send(MyMailable())`).
"""

from arvel import env

config = {
    "default": env("MAIL_MAILER", "log"),  # "log" | "smtp"
    "smtp": {
        "host": env("MAIL_HOST", "localhost"),
        "port": env("MAIL_PORT", 25),
        "username": env("MAIL_USERNAME", ""),
        "password": env("MAIL_PASSWORD", ""),
        "encryption": env("MAIL_ENCRYPTION", ""),  # "tls" | "ssl" | ""
        "timeout": env("MAIL_TIMEOUT", 30),
    },
}
