"""Clasificar exclusivamente el hostname de la URL, sin reglas de contenido."""
from urllib.parse import urlsplit


def fuente_especifica(url):
    try:
        partes = urlsplit(url)
        if partes.scheme not in ('http', 'https'):
            return 'WEB'
        host = (partes.hostname or '').lower().rstrip('.')
    except (TypeError, ValueError):
        return 'WEB'
    for fuente, dominios in (
        ('YOUTUBE', ('youtube.com', 'youtu.be', 'youtube-nocookie.com')),
        ('FACEBOOK', ('facebook.com', 'fb.com', 'fb.watch')),
        ('INSTAGRAM', ('instagram.com',)), ('X', ('x.com', 'twitter.com')),
        ('OFICIAL', ('gov.ar', 'gob.ar')),
    ):
        if any(host == d or host.endswith('.' + d) for d in dominios):
            return fuente
    return 'WEB'
