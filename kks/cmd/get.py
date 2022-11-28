from pathlib import Path

import click

from kks.util.click import ArgNotRequiredIf, RequiredIf
from kks.util.common import format_file
from kks.util.ejudge import EjudgeSession, Links, Page
from urllib.parse import parse_qs, urlsplit


@click.command(short_help='Download a file from ejudge')
@click.option('-o', '--output',
              type=click.Path(dir_okay=False, writable=True, resolve_path=True),
              cls=RequiredIf, required_if='run_id',
              help='Output file name')
@click.option('-f', '--force', is_flag=True, default=False,
              help='Force overwrite existing file')
@click.option('-r', '--run-id', type=int,
              help='Download a submission')
@click.argument('url', cls=ArgNotRequiredIf, not_required_if='run_id')
def get(output, force, run_id, url):
    """Download a file from ejudge"""
    if run_id is None:
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

    if run_id is not None:
        page = EjudgeSession().get_page(Page.DOWNLOAD_SOURCE, {'run_id': run_id})
    elif EjudgeSession.needs_auth(url):
        page = EjudgeSession().get(url)
    else:
        import requests
        page = requests.get(url)
    out_file.write_bytes(page.content)
    click.secho(
        click.style('Saved to ', fg='green') +
        format_file(out_file)
    )
