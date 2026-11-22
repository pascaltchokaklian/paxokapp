"""Development HTTPS server for testing browser features such as geolocation."""
import ssl
from pathlib import Path

from django.core.management.base import CommandError
from django.core.management.commands.runserver import Command as RunserverCommand
from django.core.servers.basehttp import WSGIServer


class SecureWSGIServer(WSGIServer):
    """Wrap the listening development-server socket with TLS."""

    ssl_context = None

    def server_activate(self):
        self.socket = self.ssl_context.wrap_socket(self.socket, server_side=True)
        super().server_activate()


class Command(RunserverCommand):
    help = 'Starts a development server over HTTPS.'

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            '--cert-file',
            required=True,
            help='Path to the PEM certificate file.',
        )
        parser.add_argument(
            '--key-file',
            required=True,
            help='Path to the PEM private key file.',
        )

    def inner_run(self, *args, **options):
        cert_file = Path(options['cert_file'])
        key_file = Path(options['key_file'])
        if not cert_file.is_file():
            raise CommandError(f'Certificate file does not exist: {cert_file}')
        if not key_file.is_file():
            raise CommandError(f'Private key file does not exist: {key_file}')

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        except ssl.SSLError as error:
            raise CommandError(f'Unable to load the TLS certificate: {error}') from error

        self.server_cls = type(
            'ConfiguredSecureWSGIServer',
            (SecureWSGIServer,),
            {'ssl_context': context},
        )
        return super().inner_run(*args, **options)
