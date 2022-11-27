from pathlib import Path

import click

from kks.util.common import format_file
from kks.util.ejudge import Links
from kks.util.h2t import HTML2Text
from kks.util.storage import Config


@click.command(short_help='Convert HTML statements to Markdown')
@click.option('-f', '--force', is_flag=True, default=False)
@click.argument('files', nargs=-1, type=click.Path(exists=True))
def convert(force, files):
    """Convert statements from HTML to Markdown (e.g. kr statements copied by scp)"""

    md_width = Config().options.mdwidth
    # NOTE baseurl may be incorrect
    converter = HTML2Text(bodywidth=md_width, baseurl=Links.WEB_CLIENT_ROOT)
    converter.pad_tables = True

    for filename in files:
        file = Path(filename)
        md_file = file.with_suffix('.md')

        if not file.is_file():
            click.secho(format_file(file), nl=False)
            click.secho(' is not a file, skipping', fg='red')
            continue
        if md_file.exists():
            if not md_file.is_file():
                click.secho(format_file(md_file), nl=False)
                click.secho(' exists and is not a file, skipping', fg='red')
                continue
            elif not force:
                click.secho(format_file(md_file), nl=False)
                click.secho(' exists, skipping (use --force to overwrite)', fg='yellow')
                continue

        md_file.write_text(converter.handle(file.read_text()))
        click.secho('Converted ', fg='green', nl=False)
        click.secho(format_file(file), nl=False)
        click.secho(' to ', fg='green', nl=False)
        click.secho(format_file(md_file))
