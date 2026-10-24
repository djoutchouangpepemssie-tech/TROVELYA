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


def identity_linked_message(*, to: str, provider: str, security_link: str) -> EmailMessage:
    """Sent when a sign-in with an external account is attached to an existing account."""
    text = (
        "Bonjour,\n\n"
        f"Votre compte {provider} vient d'être associé à votre compte TROVÉLYA : vous pouvez "
        f"désormais vous connecter avec {provider}.\n\n"
        "Si vous n'êtes pas à l'origine de cette action, sécurisez votre compte :\n"
        f"{security_link}\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    safe_provider = escape(provider)
    html = (
        "<p>Bonjour,</p>"
        f"<p>Votre compte {safe_provider} vient d'être associé à votre compte TROVÉLYA : "
        f"vous pouvez désormais vous connecter avec {safe_provider}.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette action, sécurisez votre compte :</p>"
        f'<p><a href="{escape(security_link, quote=True)}">Sécurité de mon compte</a></p>'
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(
        to=to, subject=f"{provider} a été associé à votre compte TROVÉLYA", text=text, html=html
    )


def step_up_message(*, to: str, link: str, ttl_minutes: int) -> EmailMessage:
    text = (
        "Bonjour,\n\n"
        "Pour confirmer votre identité avant une action sensible sur TROVÉLYA, ouvrez ce lien "
        "dans le même navigateur puis cliquez sur « Confirmer » :\n"
        f"{link}\n\n"
        f"Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail et vérifiez les "
        "sessions ouvertes sur votre compte.\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    html = (
        "<p>Bonjour,</p>"
        "<p>Pour confirmer votre identité avant une action sensible sur TROVÉLYA, ouvrez ce lien "
        "dans le même navigateur puis cliquez sur « Confirmer » :</p>"
        f'<p><a href="{escape(link, quote=True)}">Confirmer mon identité</a></p>'
        f"<p>Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail et vérifiez les "
        "sessions ouvertes sur votre compte.</p>"
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(
        to=to, subject="Confirmez votre identité sur TROVÉLYA", text=text, html=html
    )


def email_change_message(*, to: str, link: str, ttl_minutes: int) -> EmailMessage:
    text = (
        "Bonjour,\n\n"
        "Pour utiliser cette adresse avec votre compte TROVÉLYA, ouvrez ce lien puis cliquez "
        "sur « Confirmer » :\n"
        f"{link}\n\n"
        f"Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.\n"
        "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : "
        "l'adresse ne sera pas modifiée.\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    html = (
        "<p>Bonjour,</p>"
        "<p>Pour utiliser cette adresse avec votre compte TROVÉLYA, ouvrez ce lien puis "
        "cliquez sur « Confirmer » :</p>"
        f'<p><a href="{escape(link, quote=True)}">Confirmer ma nouvelle adresse</a></p>'
        f"<p>Ce lien ne sert qu'une fois et expire dans {ttl_minutes} minutes.</p>"
        "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : "
        "l'adresse ne sera pas modifiée.</p>"
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(
        to=to, subject="Confirmez votre nouvelle adresse TROVÉLYA", text=text, html=html
    )


def email_changed_notice(*, to: str, security_link: str) -> EmailMessage:
    """Sent to the previous address. Names neither the new address nor any undo link."""
    text = (
        "Bonjour,\n\n"
        "L'adresse e-mail de votre compte TROVÉLYA vient d'être modifiée ; cette adresse n'est "
        "plus utilisée pour vous connecter.\n"
        "Si vous n'êtes pas à l'origine de ce changement, sécurisez votre compte et contactez "
        "le support :\n"
        f"{security_link}\n\n"
        "TROVÉLYA — La belle trouvaille"
    )
    html = (
        "<p>Bonjour,</p>"
        "<p>L'adresse e-mail de votre compte TROVÉLYA vient d'être modifiée ; cette adresse "
        "n'est plus utilisée pour vous connecter.</p>"
        "<p>Si vous n'êtes pas à l'origine de ce changement, sécurisez votre compte et "
        "contactez le support :</p>"
        f'<p><a href="{escape(security_link, quote=True)}">Sécurité de mon compte</a></p>'
        "<p>TROVÉLYA — La belle trouvaille</p>"
    )
    return EmailMessage(
        to=to, subject="L'adresse de votre compte TROVÉLYA a changé", text=text, html=html
    )
