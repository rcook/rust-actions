# Copyright (c) 2023 Richard Cook
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
from argparse import ArgumentParser, ArgumentTypeError, BooleanOptionalAction
from base64 import b64decode, b64encode
from collections import namedtuple
from subprocess import run
from tempfile import TemporaryDirectory
from uuid import uuid4
import os
import platform
import sys

# 2023-04-16: Windows GitHub runners currently have Python 3.9.13

def dir_path(*args):
    return os.path.normpath(os.path.join(*args))

def file_path(*args):
    return os.path.normpath(os.path.join(*args))

class App(namedtuple("App", ["is_no_op", "cwd", "argv", "helper_path", "signtool_path", "certificate_ext", "password_ext", "timestamp_url", "env_prefix"])):
    @staticmethod
    def make(cwd, argv):
        if platform.system().lower() == "windows":
            return App.default(cwd=cwd, argv=argv)
        else:
            return App.no_op(cwd=cwd, argv=argv)

    @staticmethod
    def no_op(cwd, argv):
        return App(
            is_no_op=True,
            cwd=cwd,
            argv=argv,
            helper_path="HELPER_PATH",
            signtool_path="SIGNTOOL_PATH",
            certificate_ext=".crt",
            password_ext=".crtpass",
            timestamp_url="TIMESTAMP_URL",
            env_prefix="RUST_TOOL_ACTION_CODE_SIGN_")

    @staticmethod
    def default(cwd, argv):
        return App(
            is_no_op=False,
            cwd=cwd,
            argv=argv,
            helper_path=file_path(__file__, "..", "generate-certificate-helper.ps1"),
            signtool_path=App.find_signtool(arch="x64"),
            certificate_ext=".crt",
            password_ext=".crtpass",
            timestamp_url="http://timestamp.digicert.com",
            env_prefix="RUST_TOOL_ACTION_CODE_SIGN_")

    @staticmethod
    def find_signtool(arch, file_name="signtool.exe"):
        program_files_dir = os.getenv("ProgramFiles(x86)")
        if program_files_dir is None:
            raise RuntimeError("Not running on Windows")

        start_dir = dir_path(program_files_dir, "Windows Kits", "10", "bin")

        """
        # Cannot use glob since this does not exist in Python 3.9.13
        matches = sorted(glob.glob(f"**\\x64\\{file_name}", root_dir=start_dir, recursive=True), reverse=True)
        if len(matches) < 1:
            raise RuntimeError(f"Could not find {file_name}")
        return file_path(start_dir, matches[0])
        """

        for root_dir, _, fs in os.walk(start_dir):
            for f in fs:
                if f.lower() == file_name.lower():
                    temp = os.path.basename(root_dir)
                    if temp.lower() == arch.lower():
                        return file_path(root_dir, f)
        raise RuntimeError(f"Could not find {file_name}")

    def show_info(self, rest):
        print(f"cwd={self.cwd}")
        print(f"argv={self.argv}")
        print(f"rest={rest}")
        print(f"helper_path={self.helper_path}")
        print(f"signtool_path={self.signtool_path}")
        print(f"timestamp_url={self.timestamp_url}")

    def generate_certificate(self, certificate_path, force):
        if self.is_no_op:
            return

        paths = SecretsPaths.parse(app=self, certificate_path=certificate_path)
        subject = "Code-signing certificate for rcook.org"
        password = str(uuid4()).replace("-", "")

        with TemporaryDirectory() as temp_dir:
            temp_path = file_path(temp_dir, "cert.pfx")
            subcommand = ["ConvertTo-SecureString", "-String", password, "-Force", "-AsPlainText"]
            command = [
                "powershell",
                "-NoProfile",
                "-Command",
                self.helper_path,
                "-PfxPath", temp_path,
                "-Subject", f"\"{subject}\"",
                "-Password", "(", *subcommand, ")"
            ]
            run(command, check=True)

            mode = "wt" if force else "xt"

            with open(temp_path, "rb") as in_f, open(paths.certificate_path, mode) as out_f:
                pfx_data = in_f.read()
                out_f.write(b64encode(pfx_data).decode("utf-8"))

            with open(paths.password_path, mode) as f:
                f.write(password)

    def sign_executable(self, secrets, executable_path):
        if self.is_no_op:
            return

        with TemporaryDirectory() as temp_dir:
            temp_path = file_path(temp_dir, "cert.pfx")
            with open(temp_path, "wb") as f:
                f.write(secrets.certificate)

            command = [
                self.signtool_path,
                "sign",
                "/f",
                temp_path,
                "/p",
                secrets.password,
                "/tr",
                self.timestamp_url,
                "/td",
                "SHA256",
                "/fd",
                "SHA256",
                executable_path
            ]
            run(command, check=True)

    def verify_executable(self, executable_path):
        if self.is_no_op:
            raise RuntimeError("Not supported on this platform")

        command = [
            self.signtool_path,
            "verify",
            "/pa",
            "/v",
            executable_path
        ]
        run(command, check=True)

class SecretsPaths(namedtuple("SecretsPaths", ["certificate_path", "password_path"])):
    @staticmethod
    def parse(app, certificate_path):
        base_path, ext = os.path.splitext(certificate_path)
        if ext != app.certificate_ext:
            raise ValueError(f"Extension of path {certificate_path} was {ext} instead of expected {app.certificate_ext}")

        return SecretsPaths(
            certificate_path=certificate_path,
            password_path=base_path + app.password_ext)

class Secrets(namedtuple("Secrets", ["certificate", "password"])):
    @staticmethod
    def load(certificate_path):
        paths = SecretsPaths.parse(certificate_path)

        with open(paths.certificate_path, "rt") as f:
            b64_certificate = f.read()

        with open(paths.password_path, "rt") as f:
            password = f.read()

        return Secrets.decode(
            b64_certificate=b64_certificate,
            password=password)

    @staticmethod
    def decode(b64_certificate, password):
        certificate = b64decode(b64_certificate)
        return Secrets(
            certificate=certificate,
            password=password)

def main(app):
    def file_path_type(s):
        return file_path(app.cwd, s)

    def file_path_must_exist_type(s):
        temp = file_path(app.cwd, s)
        if not os.path.isfile(temp):
            raise ArgumentTypeError(f"file {temp} does not exist")
        return temp

    def add_secrets_arg(parser):
        def secrets_type(s):
            temp = file_path(app.cwd, s)
            try:
                return Secrets.load(certificate_path=temp)
            except:
                raise ArgumentTypeError(f"cannot load secrets from {temp}")

        default_b64_certificate = os.getenv(f"{app.env_prefix}CRT")
        default_password = os.getenv(f"{app.env_prefix}CRTPASS")

        if default_b64_certificate is not None and default_password is not None:
            default_secrets = Secrets.decode(
                b64_certificate=default_b64_certificate,
                password=default_password)
        else:
            default_secrets = None

        if default_secrets is None:
            p.add_argument(
                "--cert",
                "-c",
                dest="secrets",
                metavar="CERTIFICATE_PATH",
                type=secrets_type,
                help="certificate path",
                required=True)
        else:
            p.add_argument(
                "--cert",
                "-c",
                dest="secrets",
                metavar="CERTIFICATE_PATH",
                type=secrets_type,
                help="certificate path",
                default=default_secrets)

    parser = ArgumentParser(prog="sign", description="Richard's Code-Signing Tool")
    subparsers = parser.add_subparsers(required=True)

    p = subparsers.add_parser(
        name="info",
        help="show information",
        description="Show information")
    p.set_defaults(
        func=lambda args: app.show_info(rest=args.rest))
    p.add_argument("rest", nargs="*")

    p = subparsers.add_parser(
        name="cert",
        help="generate certificate and password",
        description="Generate certificate and password")
    p.set_defaults(
        func=lambda args:
            app.generate_certificate(
                certificate_path=args.certificate_path,
                force=args.force))
    p.add_argument(
        "--force",
        "-f",
        dest="force",
        metavar="FORCE",
        action=BooleanOptionalAction,
        default="false",
        help="force overwrite of output files")
    p.add_argument(
        dest="certificate_path",
        metavar="CERTIFICATE_PATH",
        type=file_path_type,
        help="certificate path")

    p = subparsers.add_parser(
        name="sign",
        help="sign executable",
        description="Sign executable")
    p.set_defaults(
        func=lambda args:
            app.sign_executable(
                secrets=args.secrets,
                executable_path=args.executable_path))
    add_secrets_arg(p)
    p.add_argument(
        dest="executable_path",
        metavar="EXECUTABLE_PATH",
        type=file_path_must_exist_type,
        help="executable path")

    p = subparsers.add_parser(
        name="verify",
        help="verify executable",
        description="Verify executable")
    p.set_defaults(
        func=lambda args: app.verify_executable(executable_path=args.executable_path))
    p.add_argument(
        dest="executable_path",
        metavar="EXECUTABLE_PATH",
        type=file_path_must_exist_type,
        help="executable path")

    args = parser.parse_args(app.argv)
    args.func(args)

if __name__ == "__main__":
    main(app=App.make(cwd=os.getcwd(), argv=sys.argv[1:]))
