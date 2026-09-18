import os
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage

import boto3

from ..database import now
from .config import APP_URL, SECURE
from .models import EmailToken
from .security import digest


def send_email(recipient, subject, body):
    mode = os.getenv('MAIL_MODE', 'ses')
    if mode == 'smtp' and not SECURE:
        message = EmailMessage()
        message['From'] = os.getenv('SES_FROM_EMAIL', 'minutes@localhost.test')
        message['To'] = recipient
        message['Subject'] = subject
        message.set_content(body)
        with smtplib.SMTP(os.getenv('SMTP_HOST', 'mailpit'), int(os.getenv('SMTP_PORT', '1025')), timeout=10) as smtp:
            smtp.send_message(message)
    else:
        boto3.client('ses', region_name=os.getenv('AWS_REGION', 'eu-west-1')).send_email(
            Source=os.environ['SES_FROM_EMAIL'],
            Destination={'ToAddresses': [recipient]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}},
            },
        )


def deliver_email(recipient, subject, body):
    # Do not leak tokens, email addresses, or provider errors into application logs.
    try:
        send_email(recipient, subject, body)
    except Exception:
        import logging
        logging.getLogger(__name__).error('Transactional email delivery failed; check SES/SMTP configuration. Use resend or request recovery again.')


SUBJECTS = {'reset': 'Reset your Minutes password', 'verify': 'Verify your Minutes email', 'change_email': 'Confirm your new Minutes email'}


def email_link(session, user, purpose, tasks, recipient=None):
    raw = secrets.token_urlsafe(48)
    session.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=digest(raw), expires_at=now() + timedelta(hours=1)))
    session.commit()
    path = 'reset-password' if purpose == 'reset' else 'verify-email'
    # URL fragment keeps the bearer token out of proxy/access logs and Referer headers.
    link = f'{APP_URL}/{path}#token={raw}'
    tasks.add_task(deliver_email, recipient or user.email, SUBJECTS[purpose], f'Open this link within one hour:\n\n{link}\n\nIf you did not request this, you can ignore this email.')
