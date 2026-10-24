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
