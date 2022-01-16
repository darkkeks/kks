from pathlib import Path

import click

from kks.ejudge import Links
from kks.util.common import format_file
from kks.util.ejudge import EjudgeSession
from urllib.parse import parse_qs, urlsplit


@click.command(short_help='Download a file from ejudge')
@click.option('-o', '--output',
              type=click.Path(dir_okay=False, writable=True, resolve_path=True),
              help='Output file name')
@click.option('-f', '--force', is_flag=True, default=False,
              help='Force overwrite existing file')
@click.argument('url')
def get(output, force, url):
    """Download a file from ejudge"""
    parts = urlsplit(url)
    if parts.netloc != Links.HOST:
        click.secho(
            f'Not an ejudge URL. Use wget/curl instead.',
            fg='red', err=True
        )
        return
    if output is None:
        query = parse_qs(parts.query)
        # If file name is included in query, use it.
        # Otherwise, use the name from url path or domain name.
        output = query.get('file', [''])[0] or parts.path.rsplit('/', 1)[1] or parts.netloc

    out_file = Path(output)
    if out_file.exists() and not force:
        click.confirm(
            f'File {format_file(out_file)} already exists. Overwrite?',
            abort=True
        )
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if EjudgeSession.needs_auth(url):
        page = EjudgeSession().get(url)
    else:
        import requests
        page = requests.get(url)
    out_file.write_bytes(page.content)
    click.secho(
        click.style('Saved to ', fg='green') +
        format_file(out_file)
    )
