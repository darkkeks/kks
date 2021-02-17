import socket

import click

from kks.errors import EjudgeError
from kks.util.common import ssh_enabled
from kks.util.ejudge import load_auth_data
from kks.util.storage import Config


# defaults. we use callbacks to avoid loading config when importing this module into kks.cli
def get_hostname():
    return Config().ssh.hostname or 'sandbox.ejudge.ru'

def get_login():
    config = Config()
    return config.ssh.login or config.auth.login

def get_password():
    return Config().ssh.password

def get_mnt_dir():
    return Config().ssh.mnt_dir or '/tmp/ejudge_fuse_mnt'


@click.command(short_help='Configure ssh tunneling')
@click.option('-d', '--disable', is_flag=True)
@click.option('-h', '--hostname', default=get_hostname)
@click.option('-l', '--login', default=get_login)
@click.option('-p', '--password', default=get_password)
@click.option('--ej-fuse', default='/opt/ejudge/bin/ejudge-fuse', help='Path to ejudge-fuse on remote host')
@click.option('--ej-url', default='https://caos.ejudge.ru/cgi-bin/', help='URL for ejudge-fuse')
@click.option('--mnt-dir', default=get_mnt_dir, help='Remote mount directory')
def ssh(disable, hostname, login, password, ej_fuse, ej_url, mnt_dir):
    """Enable / disable ssh tunneling for "sync" and "submit" commands"""

    from paramiko.ssh_exception import AuthenticationException, SSHException
    from kks.util.ssh import EjudgeSSHClient

    config = Config()
    timeout = config.options.kks_ssh_timeout

    if disable:
        if ssh_enabled():
            client = None
            try:
                client = EjudgeSSHClient.create_connected(hostname, login, password, mnt_dir, timeout=timeout)
                client.unmount_ej_fuse()
            except AuthenticationException:
                click.secho('Cannot unmount remote ejudge-fuse (SSH auth error)', fg='yellow')
            except (SSHException, socket.timeout) as e:
                click.secho(f'Cannot unmount remote ejudge-fuse (SSH error: {e})', fg='yellow')
            if client is not None:
                client.close()

        del config.ssh
        config.save()
        click.secho('SSH disabled', fg='green')
        return

    auth_data = load_auth_data()
    if auth_data is None:
        click.secho('No valid auth data, please use "kks auth" first', fg='red')
        return

    if password is None:
        password = click.prompt(f'{login}\'s SSH password', hide_input=True)  # not the same as ejudge password

    try:
        client = EjudgeSSHClient.create_connected(hostname, login, password, mnt_dir, timeout=timeout)
    except AuthenticationException:
        click.secho('SSH auth error', fg='red')
        return
    except (SSHException, socket.timeout) as e:
        click.secho(f'SSH error: {e}', fg='red')
        return

    click.secho('SSH connection estabilished, trying to mount ejudge-fuse', bold=True)

    if auth_data.password is None:
        auth_data.password = click.prompt(f'{auth_data.login}\'s ejudge password', hide_input=True)

    try:
        client.mount_ej_fuse(ej_fuse, ej_url, auth_data.login, auth_data.password)
    except EjudgeError as e:
        click.secho(f'Unable to mount ejudge-fuse: {e}', fg='red')
        return
    finally:
        client.close()

    ssh_cfg = config.ssh

    ssh_cfg.hostname = hostname
    ssh_cfg.login = login
    ssh_cfg.password = password
    ssh_cfg.mnt_dir = mnt_dir
    config.save()
    click.secho('SSH + ejudge-fuse enabled', fg='green')
