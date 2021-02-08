import click

from kks.errors import EjudgeError
from kks.util.common import Config, DefaultEnv
from kks.util.ejudge import load_auth_data


# defaults. we use callbacks to avoid loading config when importing this module into kks.cli
def get_hostname():
    return Config().get('SSH', 'hostname', fallback='sandbox.ejudge.ru')

def get_login():
    return Config().get('SSH', 'login', fallback=None) or Config().get('Auth', 'login', fallback=None)

def get_password():
    return Config().get('SSH', 'password', fallback=None)

def get_mnt_dir():
    return Config().get('SSH', 'mnt_dir', fallback='/tmp/ejudge_fuse_mnt')


@click.command(short_help='Configure ssh tunneling')
@click.option('-d', '--disable', is_flag=True)
@click.option('-hn', '--hostname', default=get_hostname)
@click.option('-l', '--login', default=get_login)
@click.option('-p', '--password', default=get_password)
@click.option('--ej-fuse', default='/opt/ejudge/bin/ejudge-fuse', help='Path to ejudge-fuse on remote host')
@click.option('--ej-url', default='https://caos.ejudge.ru/cgi-bin/', help='URL for ejudge-fuse')
@click.option('--mnt-dir', default=get_mnt_dir, help='Remote mount directory')
def ssh(disable, hostname, login, password, ej_fuse, ej_url, mnt_dir):
    """Enable / disable ssh tunneling for "sync" and "submit" commands"""

    from paramiko.ssh_exception import AuthenticationException, SSHException
    from kks.util.ssh import EjudgeSSHClient
    # TODO add public key auth (also no-store-password?)

    config = Config()
    if disable:
        if config.has_section('SSH'):
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
        config.save()
        click.secho('SSH disabled', fg='green')
        return

    auth_data = load_auth_data()
    if auth_data is None:
        click.secho('No valid auth data, please use "kks auth" first', fg='red')
        return

    if password is None:
        password = click.prompt(f'{login}\'s SSH password', hide_input=True)  # not the same as ejudge password

    ssh_cfg = {
        'hostname': hostname,
        'login': login,
        'password': password,
        'mnt_dir': mnt_dir
    }

    timeout = int(environ.get('KKS_SSH_TIMEOUT', DefaultEnv.KKS_SSH_TIMEOUT))
    try:
        client = EjudgeSSHClient(ssh_cfg['hostname'], ssh_cfg['login'], ssh_cfg['password'], ssh_cfg['mnt_dir'], timeout)
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

    config['SSH'] = ssh_cfg
    config.save()
    click.secho('SSH + ejudge-fuse enabled', fg='green')
