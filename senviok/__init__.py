"""Senviok — Python client for the Senviok messaging API.

Simple, typed access to email, SMS and WhatsApp messaging plus the resources
around it (webhooks, templates, domains, audiences, contacts, suppressions,
API keys and message logs).

Usage::

    from senviok import Senviok

    senviok = Senviok("svk_live_xxx")

    message = senviok.emails.send(
        from_="Acme <onboarding@acme.com>",
        to="dev@acme.com",
        subject="Hello from Senviok",
        html="<p>Hello!</p>",
    )
    print(message.id)
"""

from .client import (
    DEFAULT_BASE_URL,
    LOCAL_BASE_URL,
    AsyncSenviok,
    Senviok,
    SenviokClient,
)
from .errors import ApiError, AuthenticationError, RateLimitError, SenviokError
from .models import (
    ApiKey,
    ApiKeyCreated,
    Audience,
    Contact,
    DkimResponse,
    DkimToken,
    Domain,
    EmailAttachment,
    EmailOptions,
    EmailResponse,
    MessageLog,
    SmsResponse,
    Suppression,
    Template,
    UploadedEmailAttachment,
    VerifyDomainResponse,
    Webhook,
    WebhookDelivery,
)

__version__ = "0.1.0"

__all__ = [
    "Senviok",
    "SenviokClient",
    "AsyncSenviok",
    "SenviokError",
    "AuthenticationError",
    "RateLimitError",
    "ApiError",
    "EmailOptions",
    "EmailAttachment",
    "UploadedEmailAttachment",
    "EmailResponse",
    "SmsResponse",
    "Domain",
    "DkimToken",
    "DkimResponse",
    "VerifyDomainResponse",
    "ApiKey",
    "ApiKeyCreated",
    "Audience",
    "Contact",
    "Webhook",
    "WebhookDelivery",
    "Template",
    "Suppression",
    "MessageLog",
    "DEFAULT_BASE_URL",
    "LOCAL_BASE_URL",
    "__version__",
]
