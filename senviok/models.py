"""Request and response models for the Senviok API.

Request payloads are plain dataclasses; unknown keys passed to ``send`` and
friends raise ``TypeError`` at the call site instead of being silently dropped.
Responses are pydantic models that accept both the API's camelCase fields and
snake_case field names.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


def to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class _RequestMixin:
    """Serializes a dataclass to a JSON-safe dict, omitting unset fields."""

    def to_dict(self) -> Dict[str, Any]:
        mapping = {}
        for field_ in fields(self):  # type: ignore[arg-type]
            value = getattr(self, field_.name)
            if value is None:
                continue
            if isinstance(value, _RequestMixin):
                value = value.to_dict()
            elif isinstance(value, list):
                value = [item.to_dict() if isinstance(item, _RequestMixin) else item for item in value]
            mapping[to_camel(field_.name)] = value
        return mapping


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


@dataclass
class EmailAttachment(_RequestMixin):
    """An outgoing file. Provide exactly one of ``content`` or ``path``."""

    filename: str
    content: Optional[Union[str, bytes]] = None
    content_type: Optional[str] = None
    path: Optional[str] = None
    content_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        if bool(self.content) == bool(self.path):
            raise ValueError("Provide exactly one of attachment content or path")
        values = super().to_dict()
        if isinstance(self.content, bytes):
            values["content"] = base64.b64encode(self.content).decode("ascii")
        return values


@dataclass
class EmailOptions(_RequestMixin):
    """Options for :meth:`senviok.client.Senviok.emails.send`."""

    from_: Optional[str] = None
    from_name: Optional[str] = None
    to: Optional[Union[str, List[str]]] = None
    subject: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    cc: Optional[Union[str, List[str]]] = None
    bcc: Optional[Union[str, List[str]]] = None
    reply_to: Optional[Union[str, List[str]]] = None
    template_id: Optional[str] = None
    template_data: Optional[Dict[str, str]] = None
    add_unsubscribe_footer: Optional[bool] = None
    add_list_unsubscribe_header: Optional[bool] = None
    attachments: Optional[List[EmailAttachment]] = None
    attachment_ids: Optional[List[str]] = None


@dataclass
class SmsRequest(_RequestMixin):
    to: str
    from_: str
    text: str


@dataclass
class CreateDomainRequest(_RequestMixin):
    name: str


@dataclass
class CreateApiKeyRequest(_RequestMixin):
    name: str


@dataclass
class CreateAudienceRequest(_RequestMixin):
    name: str


@dataclass
class CreateContactRequest(_RequestMixin):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    unsubscribed: Optional[bool] = None


@dataclass
class CreateWebhookRequest(_RequestMixin):
    url: str
    events: List[str]


@dataclass
class CreateTemplateRequest(_RequestMixin):
    name: str
    subject: Optional[str] = None
    html_content: Optional[str] = None


@dataclass
class UpdateTemplateRequest(_RequestMixin):
    name: Optional[str] = None
    subject: Optional[str] = None
    html_content: Optional[str] = None


@dataclass
class CreateSuppressionRequest(_RequestMixin):
    email: str
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EmailResponse(_Model):
    id: str


class UploadedEmailAttachment(_Model):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    bucket: Optional[str] = None
    key: Optional[str] = None


class SmsResponse(_Model):
    id: str


class Domain(_Model):
    id: str
    name: str
    status: str
    created_at: Optional[str] = None


class DkimToken(_Model):
    name: str
    value: str
    type: str
    status: Optional[bool] = None


class DkimResponse(_Model):
    status: str
    tokens: List[DkimToken] = []


class VerifyDomainResponse(_Model):
    status: str
    message: Optional[str] = None
    # Raw provider diagnostics, kept untyped on purpose: the backend can add
    # per-record status fields without breaking the SDK.
    diagnostics: Optional[Dict[str, Any]] = None


class ApiKeyCreated(_Model):
    id: str
    name: str
    token: str
    created_at: str


class ApiKey(_Model):
    id: str
    name: str
    prefix: str
    created_at: Optional[str] = None


class Audience(_Model):
    id: str
    name: str
    created_at: Optional[str] = None


class Contact(_Model):
    id: str
    audience_id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    unsubscribed: Optional[bool] = None
    created_at: Optional[str] = None


class Webhook(_Model):
    id: str
    url: str
    secret: str
    events: List[str] = []
    created_at: Optional[str] = None


class WebhookDelivery(_Model):
    id: str
    webhook_id: str
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    attempt: Optional[int] = None
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None


class Template(_Model):
    id: str
    name: str
    subject: Optional[str] = None
    html_content: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Suppression(_Model):
    id: str
    email: str
    reason: Optional[str] = None
    created_at: Optional[str] = None


class MessageLog(_Model):
    id: str
    channel: str
    status: str
    to_address: Optional[str] = None
    from_address: Optional[str] = None
    subject: Optional[str] = None
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    provider_message_id: Optional[str] = None
    cc_address: Optional[str] = None
    bcc_address: Optional[str] = None
    reply_to_address: Optional[str] = None
    created_at: Optional[str] = None
