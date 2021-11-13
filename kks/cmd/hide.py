import click

from kks.util.common import find_workspace, get_hidden_dir, get_contest_dir, read_contests


@click.command()
@click.option('-a', '--all', 'all_', is_flag=True, default=False,
              help='Hide all synced contests')
@click.argument('contests', type=click.Path(), nargs=-1)
def hide(contests, all_):
    """hide directories for specified contests"""
    _make_hidden(contests, all_, True)


@click.command()
@click.option('-a', '--all', 'all_', is_flag=True, default=False,
              help='Hide all synced contests')
@click.argument('contests', type=click.Path(), nargs=-1)
def unhide(contests, all_):
    """unhide directories for specified contests"""
    _make_hidden(contests, all_, False)


def _make_hidden(contests, all_, hidden):
    workspace = find_workspace()
    if workspace is None:
        click.secho('You have to run this command under kks workspace', fg='red', err=True)
        return

    valid_contests = read_contests(workspace)
    if len(valid_contests) == 0:  # index was not created yet
        click.secho(
            f'Inconsistent workspace, run "kks sync" to enable contest hiding',
            fg='yellow', err=True
        )
        return

    if all_:
        contests = valid_contests

    for contest in contests:
        is_valid_contest = contest in valid_contests
        if is_valid_contest:
            contest_dir = get_contest_dir(workspace, contest)
            is_valid_contest = contest_dir.exists()

        if not is_valid_contest:
            click.secho(
                f'Contest {contest} does not exist (or wasnt synced)', fg='yellow', err=True
            )
            continue

        hidden_dir = get_hidden_dir(workspace)
        if not hidden_dir.exists():
            hidden_dir.mkdir()
        if hidden:
            if hidden_dir == contest_dir.parent and not all_:
                click.secho(f'Contest {contest} is already hidden', fg='yellow')
            else:
                contest_dir.rename(hidden_dir / contest_dir.name)
        else:
            if hidden_dir != contest_dir.parent and not all_:
                click.secho(f'Contest {contest} is not hidden', fg='yellow')
            else:
                contest_dir.rename(workspace / contest_dir.name)
