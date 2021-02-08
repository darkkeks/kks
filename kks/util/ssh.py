import json
import re
import shlex
from pathlib import PurePosixPath
from socket import timeout
from time import sleep

import click
from paramiko.client import SSHClient, AutoAddPolicy
from paramiko.ssh_exception import SSHException

from kks.ejudge import APIStatement, BasicAPIProblem
from kks.errors import EjudgeFuseError, APIError


EJ_FUSE_BUFSIZE = 4096


class EjudgeSSHClient(SSHClient):
    def __init__(self, hostname, login, password, mnt_dir=None, contest=None, timeout=None):
        super().__init__()
        self.hostname = hostname
        self.login = login
        self.password = password
        self.contest = contest
        self._timeout = timeout
        self._root = PurePosixPath(mnt_dir)
        self._sftp = None
        self._sftp_fail = False
        self.set_missing_host_key_policy(AutoAddPolicy)

    def connect(self):
        super().connect(self.hostname, username=self.login, password=self.password, timeout=self._timeout, banner_timeout=self._timeout)

    @classmethod
    def create_connected(cls, *args, **kwargs):
        instance = cls(*args, **kwargs)
        instance.connect()
        return instance

    def mount_ej_fuse(self, ej_fuse_path, url, login, password):
        self.unmount_ej_fuse()
        cmd = f'mkdir -p {self._root}; {ej_fuse_path} --user {login} --url {url} {self._root} -o use_ino'
        i, o, e = self.exec_command(cmd, get_pty=True, timeout=self._timeout)
        # if we write password into i immediately, it will freeze
        # if ejudge-fuse cannot be run, output will contain a part of the error message
        output = o.read(len('Password:'))
        i.write(password + '\n')
        try:
            output += o.read()
        except timeout:
            raise EjudgeFuseError('Connection timeout')

        output = output.decode()
        if not output.startswith('Password:'):
            # bash error (cannot find/execute ejudge-fuse)
            raise EjudgeFuseError(re.sub(r'^.{,2}sh: ', '', output))
        if 'mountpoint is not empty' in output:
            raise EjudgeFuseError('ejudge-fuse already mounted')
        if 'initial login failed' in output:
            err = re.search(r'\{.*\}', output, re.S)
            if err is None:
                raise EjudgeFuseError(output.split('\n', 1))
            try:
                err_data = json.loads(err.group()).get('error', {})
                raise APIError.parse(err_data)
            except json.decoder.JSONDecodeError:
                raise EjudgeFuseError(output)

    def unmount_ej_fuse(self):
        # result is not checked
        cmd = f'fusermount -u {self._root}'
        _ = self.exec_command(cmd)

    def contest_status(self):
        file = self._root / str(self.contest) / 'info.json'
        return self._parse_api_resp(file)

    def problems(self):
        try:
            info = self.contest_status()
        except EjudgeFuseError as e:
            click.secho(f'Error: {e}', fg='red')
            return None
        return [BasicAPIProblem.parse(p) for p in info['problems']]  # add parser for common classes with API?

    def problem_status(self, problem):
        file = self._problem_dir(problem) / 'info.json'
        return self._parse_api_resp(file)

    def run_status(self, prob_id, run_id):  # is it possible to get status from ej-fuse using only run_id?
        file = self._problem_dir(prob_id) / 'runs' / str(run_id) / 'info.json'
        return self._parse_api_resp(file)

    def statement(self, prob_id):
        try:
            content = self._read_file(self._problem_dir(prob_id) / 'statement.html', lazy=True)
        except EjudgeFuseError as e:
            if 'No such file or directory' in e.args[0]:
                return APIStatement(None)
            else:
                raise
        return APIStatement(content.decode())

    def submit(self, problem, file, lang):
        # lang may be id, name or None (sm01-3)
        lang = lang or 0  # ejudge-fuse uses ID 0 for problems with no langs available

        dest_file = self._problem_dir(problem) / 'submit'/ str(lang) / '{file.name}'
        self._write_file(dest_file, file.read_bytes())

        # seems like ej-fuse doesn't return run_id, only writes it to log file
        # NOTE log is not written instantly, so we need a delay
        # It's possible to get status of the previous submission or nothing at all (instead of last submission)
        # If submissions list is not IP-restricted (not comfirmed), it's better to use API or web parser to get results
        # Alternative solution - if curl is available on ejudge sandbox, it can be used to access the API

        # 1 second delay seems reasonable (tested on ~30 submissions, only 1 incorrect result)
        sleep(1)
        log = self._tail_file(self._root / str(self.contest) / 'LOG', 50).decode()
        results = re.findall(r'submit-run (ok|fail).+ -> (\d+)', log)
        if not results:
            raise EjudgeFuseError('Unknown error - file not submitted (or ejudge-fuse did not log run_id)')

        res, run_id = results[-1]
        if res == 'ok':
            return {'run_id': int(run_id), 'run_uuid': 'unknown'}

        _, log = log.rsplit('submit-run fail', 1)
        err = re.search(r'<\s*({.+?})\s*>', log, re.S)
        if err is None:
            raise EjudgeFuseError('Ejudge API error (no additional info available)')
        err_data = json.loads(err.group(1)).get('error', {})
        raise APIError.parse(err_data)

    def _sftp_client(self):
        if self._sftp is not None:
            return self._sftp
        if self._sftp_fail:
            return None
        try:
            self._sftp = self.open_sftp()
            self._sftp.get_channel().settimeout(self._timeout)
            return self._sftp
        except SSHException as e:
            msg = str(e)
            if msg == 'Channel closed.':  # sftp disabled
                click.secho('SFTP file transfer not available, using fallback method', fg='yellow')
                self._sftp_fail = True
                return None
            raise e

    def _problem_dir(self, problem):
        # problem may be id or short name
        return self._root / str(self.contest) / 'problems' / str(problem)

    def _parse_api_resp(self, file):
        data = json.loads(self._read_file(file))
        if not data['ok']:
            raise APIError.parse(data.get('error', {}))
        return data['result']

    def _tail_file(self, file, n=10):
        data = self._read_file(file)
        return b''.join(data.splitlines(keepends=True)[-n:])

    def _read_file(self, file, lazy=False):
        """read text file from ejudge-fuse mount"""

        def get_delay():
            if not lazy:
                return 0
            try:
                stat = sftp.stat(str(file))
            except OSError as e:
                raise EjudgeFuseError(f'{e} ({file})')
            if not hasattr(stat, 'st_size') or stat.st_size == EJ_FUSE_BUFSIZE:
                # file is not loaded or size is not available
                return 1
            return 0

        sftp = self._sftp_client()

        if sftp is None:
            return self._read_fallback(file, lazy)

        try:
            with sftp.open(str(file), 'rb') as f:
                sleep(get_delay())
                return f.read()
        except timeout:
                raise EjudgeFuseError('Connection timeout')
        except OSError as e:
            raise EjudgeFuseError(f'{e} ({file})')

    def _write_file(self, file, data):
        """write binary data"""
        sftp = self._sftp_client()

        if sftp is None:
            return self._write_fallback(file, data)

        try:
            with self._sftp.open(str(file), 'wb') as f:
                f.write(data)
        except timeout:
            raise EjudgeFuseError('Connection timeout')
        except OSError as e:
            raise EjudgeFuseError(f'{e} ({file})')

    def _read_fallback(self, file, lazy):
        cmd = f'cat {shlex.quote(str(file))}'
        i, o, e = self.exec_command(cmd, timeout=self._timeout)
        try:
            data = o.read()
            if lazy and len(data) == EJ_FUSE_BUFSIZE:
                # file is being loaded by ej-fuse
                sleep(1)
                return self._read_fallback(file, False)
        except timeout:
            raise EjudgeFuseError('Connection timeout')
        err = e.read().decode()
        if err:
            raise EjudgeFuseError(err)
        return data

    def _write_fallback(self, file, data):
        cmd = f'cat > {shlex.quote(str(file))}'
        i, o, e = self.exec_command(cmd, timeout=self._timeout)
        try:
            i.write(data)
            i.channel.shutdown_write()
        except timeout:
            raise EjudgeFuseError('Connection timeout')
        err = e.read().decode()
        if err:
            raise EjudgeFuseError(err)
