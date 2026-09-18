import socketserver
from threading import Thread

from app.auth import email
from app.auth.email import send_email


class SmtpHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'220 localhost test SMTP\r\n')
        data = []
        receiving = False
        while line := self.rfile.readline():
            command = line.rstrip(b'\r\n')
            if receiving:
                if command == b'.':
                    self.server.messages.append(b'\n'.join(data).decode())
                    data = []
                    receiving = False
                    self.wfile.write(b'250 queued\r\n')
                else:
                    data.append(command[1:] if command.startswith(b'..') else command)
            elif command.upper().startswith((b'EHLO', b'HELO')):
                self.wfile.write(b'250 localhost\r\n')
            elif command.upper().startswith((b'MAIL FROM:', b'RCPT TO:')):
                self.wfile.write(b'250 ok\r\n')
            elif command.upper() == b'DATA':
                receiving = True
                self.wfile.write(b'354 end with dot\r\n')
            elif command.upper() == b'QUIT':
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                self.wfile.write(b'250 ok\r\n')


class SmtpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self):
        self.messages = []
        super().__init__(('127.0.0.1', 0), SmtpHandler)


def test_send_email_delivers_over_local_smtp(monkeypatch):
    server = SmtpServer()
    thread = Thread(target=server.serve_forever)
    thread.start()
    monkeypatch.setenv('MAIL_MODE', 'smtp')
    monkeypatch.setenv('SMTP_HOST', '127.0.0.1')
    monkeypatch.setenv('SMTP_PORT', str(server.server_address[1]))
    monkeypatch.setenv('SES_FROM_EMAIL', 'minutes@localhost.test')
    try:
        send_email('reader@example.com', 'Meeting starting soon', 'Reminder body')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert len(server.messages) == 1
    data = server.messages[0]
    assert 'From: minutes@localhost.test' in data
    assert 'To: reader@example.com' in data
    assert 'Subject: Meeting starting soon' in data
    assert 'Reminder body' in data


def test_send_email_declares_utf8_for_ses(monkeypatch):
    calls = []

    class SesClient:
        def send_email(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setenv('MAIL_MODE', 'ses')
    monkeypatch.setenv('SES_FROM_EMAIL', 'minutes@example.com')
    monkeypatch.setattr(email.boto3, 'client', lambda *args, **kwargs: SesClient())

    send_email('reader@example.com', 'Résumé — 予定', 'Olá, 世界')

    assert calls == [{
        'Source': 'minutes@example.com',
        'Destination': {'ToAddresses': ['reader@example.com']},
        'Message': {
            'Subject': {'Data': 'Résumé — 予定', 'Charset': 'UTF-8'},
            'Body': {'Text': {'Data': 'Olá, 世界', 'Charset': 'UTF-8'}},
        },
    }]
