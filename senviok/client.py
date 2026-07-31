"""Sync and async clients for the Senviok messaging API.

Mirrors the public facade of the official JavaScript SDK (``Senviok`` /
``SenviokClient``) so code ports 1:1. All 11 public resources are exposed as
properties: ``emails``, ``sms``, ``whatsapp``, ``messages``, ``webhooks``,
``templates``, ``domains``, ``audiences``, ``contacts``, ``suppressions`` and
``apiKeys``.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Dict, List, Optional, Union

import httpx

from .errors import ApiError, AuthenticationError, RateLimitError, _error_message
from .models import (
    ApiKey,
    ApiKeyCreated,
    Audience,
    Contact,
    CreateApiKeyRequest,
    CreateAudienceRequest,
    CreateContactRequest,
    CreateDomainRequest,
    CreateSuppressionRequest,
    CreateTemplateRequest,
    CreateWebhookRequest,
    DkimResponse,
    Domain,
    EmailOptions,
    EmailResponse,
    MessageLog,
    SmsRequest,
    SmsResponse,
    Suppression,
    Template,
    UpdateTemplateRequest,
    VerifyDomainResponse,
    Webhook,
    WebhookDelivery,
    to_camel,
)

DEFAULT_BASE_URL = "https://api.senviok.live"
LOCAL_BASE_URL = "http://localhost:5033"


class _Base:
    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self._base_url}/v1{path}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    @staticmethod
    def _check(response: httpx.Response) -> Any:
        if response.is_success:
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        status = response.status_code
        body = response.json() if response.content else None
        message = _error_message(body)
        if status in (401, 403):
            raise AuthenticationError(message, status_code=status)
        if status == 429:
            raise RateLimitError(message, status_code=status)
        raise ApiError(message, status_code=status, body=body)

    @staticmethod
    def _as_list(payload: Any) -> List[Any]:
        """List endpoints wrap payloads inconsistently (``data``, ``logs`` or a
        bare array); normalize all of them to a plain list."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "logs"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _query(**kwargs: Any) -> Dict[str, Any]:
        return {to_camel(k): v for k, v in kwargs.items() if v is not None}


# ---------------------------------------------------------------------------
# Sync resources
# ---------------------------------------------------------------------------


class _EmailsResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def send(self, **kwargs: Any) -> EmailResponse:
        """Send an email. Accepts the same options as the JS SDK, e.g.::

            senviok.emails.send(
                from_="Acme <onboarding@acme.com>",
                to="dev@acme.com",
                subject="Hello",
                html="<p>Hello!</p>",
            )

        Unknown keyword arguments raise ``TypeError``.
        """
        payload = EmailOptions(**kwargs).to_dict()
        data = self._client._request("POST", "/emails", json=payload)
        return EmailResponse.model_validate(data)


class _SmsResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def send(self, to: str, from_: str, text: str) -> SmsResponse:
        payload = SmsRequest(to=to, from_=from_, text=text).to_dict()
        data = self._client._request("POST", "/sms", json=payload)
        return SmsResponse.model_validate(data)


class _WhatsAppResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def send(self, to: str, from_: str, text: str) -> SmsResponse:
        payload = SmsRequest(to=to, from_=from_, text=text).to_dict()
        data = self._client._request("POST", "/whatsapp", json=payload)
        return SmsResponse.model_validate(data)


class _MessagesResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def list(
        self,
        skip: int = 0,
        take: int = 20,
        sort_order: str = "desc",
        channel: Optional[str] = None,
        status: Optional[str] = None,
        to_address: Optional[str] = None,
        from_address: Optional[str] = None,
        subject: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[MessageLog]:
        params = _Base._query(
            skip=skip,
            take=take,
            sort_order=sort_order,
            channel=channel,
            status=status,
            to_address=to_address,
            from_address=from_address,
            subject=subject,
            start_date=start_date,
            end_date=end_date,
        )
        data = self._client._request("GET", "/analytics/logs", params=params)
        return [MessageLog.model_validate(item) for item in self._client._as_list(data)]


class _WebhooksResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, url: str, events: Union[str, List[str]]) -> Webhook:
        event_list = [events] if isinstance(events, str) else events
        payload = CreateWebhookRequest(url=url, events=event_list).to_dict()
        data = self._client._request("POST", "/webhooks", json=payload)
        return Webhook.model_validate(data)

    def list(self) -> List[Webhook]:
        data = self._client._request("GET", "/webhooks")
        return [Webhook.model_validate(item) for item in self._client._as_list(data)]

    def delete(self, id: str) -> None:
        self._client._request("DELETE", f"/webhooks/{id}")

    def logs(self, webhook_id: str) -> List[WebhookDelivery]:
        data = self._client._request("GET", f"/webhooks/{webhook_id}/deliveries")
        return [WebhookDelivery.model_validate(item) for item in self._client._as_list(data)]

    @staticmethod
    def verify_signature(raw_body: Union[str, bytes], signature: str, secret: str) -> bool:
        """Constant-time HMAC-SHA256 verification of a webhook signature."""
        body = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
        try:
            computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(computed, signature)
        except (TypeError, ValueError):
            return False


class _TemplatesResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, name: str, subject: Optional[str] = None, html_content: Optional[str] = None) -> Template:
        payload = CreateTemplateRequest(name=name, subject=subject, html_content=html_content).to_dict()
        data = self._client._request("POST", "/templates", json=payload)
        return Template.model_validate(data)

    def list(self) -> List[Template]:
        data = self._client._request("GET", "/templates")
        return [Template.model_validate(item) for item in self._client._as_list(data)]

    def get(self, id: str) -> Template:
        data = self._client._request("GET", f"/templates/{id}")
        return Template.model_validate(data)

    def update(self, id: str, name: Optional[str] = None, subject: Optional[str] = None, html_content: Optional[str] = None) -> Template:
        payload = UpdateTemplateRequest(name=name, subject=subject, html_content=html_content).to_dict()
        data = self._client._request("PUT", f"/templates/{id}", json=payload)
        return Template.model_validate(data)

    def delete(self, id: str) -> None:
        self._client._request("DELETE", f"/templates/{id}")


class _DomainsResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, name: str) -> Domain:
        payload = CreateDomainRequest(name=name).to_dict()
        data = self._client._request("POST", "/domains", json=payload)
        return Domain.model_validate(data)

    def list(self) -> List[Domain]:
        data = self._client._request("GET", "/domains")
        return [Domain.model_validate(item) for item in self._client._as_list(data)]

    def get_dkim(self, id: str) -> DkimResponse:
        data = self._client._request("GET", f"/domains/{id}/dkim")
        return DkimResponse.model_validate(data)

    def verify(self, id: str) -> VerifyDomainResponse:
        data = self._client._request("POST", f"/domains/{id}/verify")
        return VerifyDomainResponse.model_validate(data)


class _AudiencesResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, name: str) -> Audience:
        payload = CreateAudienceRequest(name=name).to_dict()
        data = self._client._request("POST", "/audiences", json=payload)
        return Audience.model_validate(data)

    def list(self) -> List[Audience]:
        data = self._client._request("GET", "/audiences")
        return [Audience.model_validate(item) for item in self._client._as_list(data)]

    def delete(self, id: str) -> None:
        self._client._request("DELETE", f"/audiences/{id}")


class _ContactsResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(
        self,
        audience_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        unsubscribed: Optional[bool] = None,
    ) -> Contact:
        payload = CreateContactRequest(
            email=email, first_name=first_name, last_name=last_name, unsubscribed=unsubscribed
        ).to_dict()
        data = self._client._request("POST", f"/audiences/{audience_id}/contacts", json=payload)
        return Contact.model_validate(data)

    def list(self, audience_id: str) -> List[Contact]:
        data = self._client._request("GET", f"/audiences/{audience_id}/contacts")
        return [Contact.model_validate(item) for item in self._client._as_list(data)]

    def delete(self, audience_id: str, id: str) -> None:
        self._client._request("DELETE", f"/audiences/{audience_id}/contacts/{id}")


class _SuppressionsResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, email: str, reason: Optional[str] = None) -> Suppression:
        payload = CreateSuppressionRequest(email=email, reason=reason).to_dict()
        data = self._client._request("POST", "/suppressions", json=payload)
        return Suppression.model_validate(data)

    def list(self) -> List[Suppression]:
        data = self._client._request("GET", "/suppressions")
        return [Suppression.model_validate(item) for item in self._client._as_list(data)]

    def delete(self, id: str) -> None:
        self._client._request("DELETE", f"/suppressions/{id}")


class _ApiKeysResource:
    def __init__(self, client: "Senviok"):
        self._client = client

    def create(self, name: str) -> ApiKeyCreated:
        payload = CreateApiKeyRequest(name=name).to_dict()
        data = self._client._request("POST", "/api-keys", json=payload)
        return ApiKeyCreated.model_validate(data)

    def list(self) -> List[ApiKey]:
        data = self._client._request("GET", "/api-keys")
        return [ApiKey.model_validate(item) for item in self._client._as_list(data)]

    def delete(self, id: str) -> None:
        self._client._request("DELETE", f"/api-keys/{id}")


# ---------------------------------------------------------------------------
# Sync client
# ---------------------------------------------------------------------------


class Senviok(_Base):
    """Synchronous Senviok client.

    :param api_key: API key (``svk_live_*`` / ``svk_test_*``).
    :param base_url: Defaults to the production API. Use
        ``Senviok(api_key, base_url="http://localhost:5033")`` for local dev.
    :param timeout: Request timeout in seconds.

    Usage::

        from senviok import Senviok

        senviok = Senviok("svk_live_xxx")
        senviok.emails.send(from_="hi@example.com", to="user@example.com",
                            subject="Hi", html="<p>Hi</p>")
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        super().__init__(api_key, base_url, timeout)
        self._client = httpx.Client(timeout=timeout)
        self.emails = _EmailsResource(self)
        self.sms = _SmsResource(self)
        self.whatsapp = _WhatsAppResource(self)
        self.messages = _MessagesResource(self)
        self.webhooks = _WebhooksResource(self)
        self.templates = _TemplatesResource(self)
        self.domains = _DomainsResource(self)
        self.audiences = _AudiencesResource(self)
        self.contacts = _ContactsResource(self)
        self.suppressions = _SuppressionsResource(self)
        self.api_keys = _ApiKeysResource(self)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, self._url(path), headers=self._headers(), **kwargs)
        return self._check(response)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Senviok":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Async resources
# ---------------------------------------------------------------------------


class _AsyncEmailsResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def send(self, **kwargs: Any) -> EmailResponse:
        payload = EmailOptions(**kwargs).to_dict()
        data = await self._client._request("POST", "/emails", json=payload)
        return EmailResponse.model_validate(data)


class _AsyncSmsResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def send(self, to: str, from_: str, text: str) -> SmsResponse:
        payload = SmsRequest(to=to, from_=from_, text=text).to_dict()
        data = await self._client._request("POST", "/sms", json=payload)
        return SmsResponse.model_validate(data)


class _AsyncWhatsAppResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def send(self, to: str, from_: str, text: str) -> SmsResponse:
        payload = SmsRequest(to=to, from_=from_, text=text).to_dict()
        data = await self._client._request("POST", "/whatsapp", json=payload)
        return SmsResponse.model_validate(data)


class _AsyncMessagesResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def list(
        self,
        skip: int = 0,
        take: int = 20,
        sort_order: str = "desc",
        channel: Optional[str] = None,
        status: Optional[str] = None,
        to_address: Optional[str] = None,
        from_address: Optional[str] = None,
        subject: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[MessageLog]:
        params = _Base._query(
            skip=skip,
            take=take,
            sort_order=sort_order,
            channel=channel,
            status=status,
            to_address=to_address,
            from_address=from_address,
            subject=subject,
            start_date=start_date,
            end_date=end_date,
        )
        data = await self._client._request("GET", "/analytics/logs", params=params)
        return [MessageLog.model_validate(item) for item in self._client._as_list(data)]


class _AsyncWebhooksResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, url: str, events: Union[str, List[str]]) -> Webhook:
        event_list = [events] if isinstance(events, str) else events
        payload = CreateWebhookRequest(url=url, events=event_list).to_dict()
        data = await self._client._request("POST", "/webhooks", json=payload)
        return Webhook.model_validate(data)

    async def list(self) -> List[Webhook]:
        data = await self._client._request("GET", "/webhooks")
        return [Webhook.model_validate(item) for item in self._client._as_list(data)]

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/webhooks/{id}")

    async def logs(self, webhook_id: str) -> List[WebhookDelivery]:
        data = await self._client._request("GET", f"/webhooks/{webhook_id}/deliveries")
        return [WebhookDelivery.model_validate(item) for item in self._client._as_list(data)]

    @staticmethod
    def verify_signature(raw_body: Union[str, bytes], signature: str, secret: str) -> bool:
        return _WebhooksResource.verify_signature(raw_body, signature, secret)


class _AsyncTemplatesResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, name: str, subject: Optional[str] = None, html_content: Optional[str] = None) -> Template:
        payload = CreateTemplateRequest(name=name, subject=subject, html_content=html_content).to_dict()
        data = await self._client._request("POST", "/templates", json=payload)
        return Template.model_validate(data)

    async def list(self) -> List[Template]:
        data = await self._client._request("GET", "/templates")
        return [Template.model_validate(item) for item in self._client._as_list(data)]

    async def get(self, id: str) -> Template:
        data = await self._client._request("GET", f"/templates/{id}")
        return Template.model_validate(data)

    async def update(self, id: str, name: Optional[str] = None, subject: Optional[str] = None, html_content: Optional[str] = None) -> Template:
        payload = UpdateTemplateRequest(name=name, subject=subject, html_content=html_content).to_dict()
        data = await self._client._request("PUT", f"/templates/{id}", json=payload)
        return Template.model_validate(data)

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/templates/{id}")


class _AsyncDomainsResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, name: str) -> Domain:
        payload = CreateDomainRequest(name=name).to_dict()
        data = await self._client._request("POST", "/domains", json=payload)
        return Domain.model_validate(data)

    async def list(self) -> List[Domain]:
        data = await self._client._request("GET", "/domains")
        return [Domain.model_validate(item) for item in self._client._as_list(data)]

    async def get_dkim(self, id: str) -> DkimResponse:
        data = await self._client._request("GET", f"/domains/{id}/dkim")
        return DkimResponse.model_validate(data)

    async def verify(self, id: str) -> VerifyDomainResponse:
        data = await self._client._request("POST", f"/domains/{id}/verify")
        return VerifyDomainResponse.model_validate(data)


class _AsyncAudiencesResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, name: str) -> Audience:
        payload = CreateAudienceRequest(name=name).to_dict()
        data = await self._client._request("POST", "/audiences", json=payload)
        return Audience.model_validate(data)

    async def list(self) -> List[Audience]:
        data = await self._client._request("GET", "/audiences")
        return [Audience.model_validate(item) for item in self._client._as_list(data)]

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/audiences/{id}")


class _AsyncContactsResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(
        self,
        audience_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        unsubscribed: Optional[bool] = None,
    ) -> Contact:
        payload = CreateContactRequest(
            email=email, first_name=first_name, last_name=last_name, unsubscribed=unsubscribed
        ).to_dict()
        data = await self._client._request("POST", f"/audiences/{audience_id}/contacts", json=payload)
        return Contact.model_validate(data)

    async def list(self, audience_id: str) -> List[Contact]:
        data = await self._client._request("GET", f"/audiences/{audience_id}/contacts")
        return [Contact.model_validate(item) for item in self._client._as_list(data)]

    async def delete(self, audience_id: str, id: str) -> None:
        await self._client._request("DELETE", f"/audiences/{audience_id}/contacts/{id}")


class _AsyncSuppressionsResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, email: str, reason: Optional[str] = None) -> Suppression:
        payload = CreateSuppressionRequest(email=email, reason=reason).to_dict()
        data = await self._client._request("POST", "/suppressions", json=payload)
        return Suppression.model_validate(data)

    async def list(self) -> List[Suppression]:
        data = await self._client._request("GET", "/suppressions")
        return [Suppression.model_validate(item) for item in self._client._as_list(data)]

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/suppressions/{id}")


class _AsyncApiKeysResource:
    def __init__(self, client: "AsyncSenviok"):
        self._client = client

    async def create(self, name: str) -> ApiKeyCreated:
        payload = CreateApiKeyRequest(name=name).to_dict()
        data = await self._client._request("POST", "/api-keys", json=payload)
        return ApiKeyCreated.model_validate(data)

    async def list(self) -> List[ApiKey]:
        data = await self._client._request("GET", "/api-keys")
        return [ApiKey.model_validate(item) for item in self._client._as_list(data)]

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/api-keys/{id}")


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


class AsyncSenviok(_Base):
    """Asynchronous Senviok client — same facade as :class:`Senviok`, but every
    resource method is a coroutine::

        import asyncio
        from senviok import AsyncSenviok

        async def main():
            senviok = AsyncSenviok("svk_live_xxx")
            await senviok.emails.send(from_="hi@example.com", to="user@example.com",
                                      subject="Hi", html="<p>Hi</p>")

        asyncio.run(main())
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0):
        super().__init__(api_key, base_url, timeout)
        self._client = httpx.AsyncClient(timeout=timeout)
        self.emails = _AsyncEmailsResource(self)
        self.sms = _AsyncSmsResource(self)
        self.whatsapp = _AsyncWhatsAppResource(self)
        self.messages = _AsyncMessagesResource(self)
        self.webhooks = _AsyncWebhooksResource(self)
        self.templates = _AsyncTemplatesResource(self)
        self.domains = _AsyncDomainsResource(self)
        self.audiences = _AsyncAudiencesResource(self)
        self.contacts = _AsyncContactsResource(self)
        self.suppressions = _AsyncSuppressionsResource(self)
        self.api_keys = _AsyncApiKeysResource(self)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, self._url(path), headers=self._headers(), **kwargs)
        return self._check(response)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncSenviok":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


# Backwards-compatible alias matching the JS SDK's class name.
SenviokClient = Senviok

__all__ = [
    "Senviok",
    "SenviokClient",
    "AsyncSenviok",
    "DEFAULT_BASE_URL",
    "LOCAL_BASE_URL",
]
