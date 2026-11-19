"""Async client tests (pytest-asyncio)."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import respx

from senviok import AsyncSenviok

API_KEY = "svk_live_test_123"
BASE = "https://api.senviok.live"


@pytest.mark.asyncio
@respx.mock
async def test_async_send_email() -> None:
    respx.post(f"{BASE}/v1/emails").mock(return_value=httpx.Response(200, json={"id": "msg_async"}))

    async with AsyncSenviok(api_key=API_KEY) as senviok:
        result = await senviok.emails.send(
            from_="hi@example.com", to="user@example.com", subject="Hi", html="<p>Hi</p>"
        )

    assert result.id == "msg_async"


@pytest.mark.asyncio
@respx.mock
async def test_async_upload_then_send_attachment() -> None:
    upload = respx.post(f"{BASE}/v1/emails/attachments").mock(return_value=httpx.Response(200, json={
        "id": "att_async", "filename": "photo.png", "contentType": "image/png",
        "sizeBytes": 3, "bucket": "test", "key": "test/att_async",
    }))
    send = respx.post(f"{BASE}/v1/emails").mock(return_value=httpx.Response(200, json={"id": "msg_async"}))

    async with AsyncSenviok(api_key=API_KEY) as senviok:
        uploaded = await senviok.emails.upload_attachment(b"png", "photo.png", "image/png")
        result = await senviok.emails.send(
            from_="hello@example.com", to="user@example.com", subject="Photo",
            attachment_ids=[uploaded.id],
        )

    assert result.id == "msg_async"
    assert upload.calls.last.request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'filename="photo.png"' in upload.calls.last.request.content
    assert json.loads(send.calls.last.request.content)["attachmentIds"] == ["att_async"]


@pytest.mark.asyncio
@respx.mock
async def test_async_messages_and_domains() -> None:
    respx.get(f"{BASE}/v1/analytics/logs").mock(
        return_value=httpx.Response(200, json={"logs": [{"id": "l1", "channel": "sms", "status": "queued"}]})
    )
    respx.get(f"{BASE}/v1/domains").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "d1", "name": "x.com", "status": "pending"}]})
    )

    async with AsyncSenviok(api_key=API_KEY) as senviok:
        logs = await senviok.messages.list(take=5)
        domains = await senviok.domains.list()

    assert logs[0].channel == "sms"
    assert domains[0].name == "x.com"


@pytest.mark.asyncio
@respx.mock
async def test_async_error_mapping() -> None:
    respx.get(f"{BASE}/v1/webhooks").mock(return_value=httpx.Response(429, json={"message": "slow down"}))

    async with AsyncSenviok(api_key=API_KEY) as senviok:
        from senviok.errors import RateLimitError

        with pytest.raises(RateLimitError):
            await senviok.webhooks.list()


def test_async_verify_signature_matches_sync() -> None:
    secret = "whsec_async"
    raw = b'{"event":"delivered"}'
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    assert AsyncSenviok(API_KEY).webhooks.verify_signature(raw, sig, secret) is True
    assert AsyncSenviok(API_KEY).webhooks.verify_signature(raw, "bad", secret) is False
