import click

from kks.errors import EjudgeError
from kks.util.common import read_config, write_config
from kks.util.ejudge import load_auth_data


@click.command(short_help='Configure ssh tunneling')
@click.option('-d', '--disable', is_flag=True)
@click.option('-hn', '--hostname')
@click.option('-l', '--login')
@click.option('-p', '--password')
@click.option('--ej-fuse', default='/opt/ejudge/bin/ejudge-fuse', help='Path to ejudge-fuse on remote host')
@click.option('--ej-url', default='https://caos.ejudge.ru/cgi-bin/', help='URL for ejudge-fuse')
@click.option('--mnt-dir', help='Remote mount directory')
def ssh(disable, hostname, login, password, ej_fuse, ej_url, mnt_dir):
    """Enable / disable ssh tunneling for "sync" and "submit" commands"""

    from paramiko.ssh_exception import AuthenticationException, SSHException
    from kks.util.ssh import EjudgeSSHClient
    # TODO add public key auth (also no-store-password?)

    config = read_config()
    if disable:
        if config.has_section('SSH'):
            ssh_cfg = config['SSH']
            hostname = hostname or ssh_cfg['hostname']
            login = login or ssh_cfg['login']
            password = password or config['SSH'].get('password')
            mnt_dir = mnt_dir or ssh_cfg['mnt_dir']

            try:
                client = EjudgeSSHClient(hostname, login, password, mnt_dir)
            except AuthenticationException:
                click.secho('Cannot unmount remote ejudge-fuse (SSH auth error)', fg='yellow')
            except SSHException as e:
                click.secho(f'Cannot unmount remote ejudge-fuse (SSH error: {e})', fg='yellow')
            else:
                client.unmount_ej_fuse()
                client.close()

        config.remove_section('SSH')
        write_config(config)
        click.secho('SSH disabled', fg='green')
        return

    auth_data = load_auth_data()
    if auth_data is None:
        click.secho('No valid auth data, please use "kks auth" first', fg='red')
        return

    if password is None:
        password = click.prompt(f'{auth_data.login}\'s SSH password', hide_input=True)  # not the same as ejudge password

    ssh_cfg = config['SSH'] = {
        'hostname': hostname or 'sandbox.ejudge.ru',
        'login': login or auth_data.login,
        'password': password,
        'mnt_dir': mnt_dir or '/tmp/ejudge_fuse_mnt'
    }

    try:
        client = EjudgeSSHClient(ssh_cfg['hostname'], ssh_cfg['login'], ssh_cfg['password'], ssh_cfg['mnt_dir'])
    except AuthenticationException:
        click.secho('SSH auth error', fg='red')
        return

    click.secho('SSH connection estabilished, trying to mount ejudge-fuse', bold=True)
    try:
        client.mount_ej_fuse(ej_fuse, ej_url, auth_data.login, auth_data.password)
    except EjudgeError as e:
        click.secho(f'Unable to mount ejudge-fuse: {e}', fg='red')
        return
    finally:
        client.close()

    write_config(config)
    click.secho('SSH + ejudge-fuse enabled', fg='green')
