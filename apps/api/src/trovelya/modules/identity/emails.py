"""E-mails sent by the identity module (French, plain text + HTML)."""

from html import escape

from trovelya.shared.email import EmailMessage


def magic_link_message(*, to: str, link: str, ttl_minutes: int) -> EmailMessage:
    text = (
        "Bonjour,\n\n"
        "Pour vous connecter à TROVÉLYA, ouvrez ce lien puis cliquez sur « Me connecter » :\n"
        f"{link}\n\n"
        f"Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : "
        "personne ne pourra se connecter sans ce lien.\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    safe = escape(link, quote=True)
    html = (
        "<p>Bonjour,</p>"
        "<p>Pour vous connecter à TROVÉLYA, ouvrez ce lien puis cliquez sur "
        "« Me connecter » :</p>"
        f'<p><a href="{safe}">Me connecter à TROVÉLYA</a></p>'
        f"<p>Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : "
        "personne ne pourra se connecter sans ce lien.</p>"
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(to=to, subject="Votre lien de connexion TROVÉLYA", text=text, html=html)


def new_login_message(
    *, to: str, when: str, device: str, country: str, security_link: str
) -> EmailMessage:
    """Alert for a sign-in from a new device or country. Never the IP address (PII.md)."""
    details = [f"Date : {when}", f"Appareil : {device}", f"Pays : {country}"]
    text = (
        "Bonjour,\n\n"
        "Une nouvelle connexion à votre compte TROVÉLYA vient d'avoir lieu :\n"
        + "".join(f"- {line}\n" for line in details)
        + "\nSi c'est vous, vous n'avez rien à faire.\n"
        "Sinon, déconnectez cet appareil et vérifiez vos moyens de connexion :\n"
        f"{security_link}\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    safe_link = escape(security_link, quote=True)
    html = (
        "<p>Bonjour,</p>"
        "<p>Une nouvelle connexion à votre compte TROVÉLYA vient d'avoir lieu :</p>"
        "<ul>" + "".join(f"<li>{escape(line)}</li>" for line in details) + "</ul>"
        "<p>Si c'est vous, vous n'avez rien à faire.</p>"
        "<p>Sinon, déconnectez cet appareil et vérifiez vos moyens de connexion :</p>"
        f'<p><a href="{safe_link}">Sécurité de mon compte</a></p>'
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(
        to=to, subject="Nouvelle connexion à votre compte TROVÉLYA", text=text, html=html
    )
