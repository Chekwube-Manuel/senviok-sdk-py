"""End-to-end tests for the Senviok SDK using mocked HTTP (respx)."""

from __future__ import annotations

import json
from io import BytesIO

import httpx
import pytest
import respx

from senviok import Senviok
from senviok.errors import ApiError, AuthenticationError, RateLimitError

API_KEY = "svk_live_test_123"
BASE = "https://api.senviok.live"


@pytest.fixture
def senviok() -> Senviok:
    return Senviok(api_key=API_KEY)


@respx.mock
def test_send_email_builds_correct_request(senviok: Senviok) -> None:
    route = respx.post(f"{BASE}/v1/emails").mock(
        return_value=httpx.Response(200, json={"id": "msg_123"})
    )

    result = senviok.emails.send(
        from_="Acme <onboarding@acme.com>",
        to=["dev@acme.com", "ops@acme.com"],
        subject="Hello",
        html="<p>Hi</p>",
        add_unsubscribe_footer=True,
    )

    assert result.id == "msg_123"
    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "from": "Acme <onboarding@acme.com>",
        "to": ["dev@acme.com", "ops@acme.com"],
        "subject": "Hello",
        "html": "<p>Hi</p>",
        "addUnsubscribeFooter": True,
    }


def test_send_email_unknown_option_raises_type_error(senviok: Senviok) -> None:
    with pytest.raises(TypeError):
        senviok.emails.send(bogus_option="nope")  # type: ignore[call-arg]


@respx.mock
def test_upload_then_send_attachment(senviok: Senviok) -> None:
    upload = respx.post(f"{BASE}/v1/emails/attachments").mock(return_value=httpx.Response(200, json={
        "id": "att_123", "filename": "invoice.pdf", "contentType": "application/pdf",
        "sizeBytes": 3, "bucket": "test", "key": "test/att_123",
    }))
    send = respx.post(f"{BASE}/v1/emails").mock(return_value=httpx.Response(200, json={"id": "msg_123"}))

    uploaded = senviok.emails.upload_attachment(BytesIO(b"pdf"), "invoice.pdf", "application/pdf")
    result = senviok.emails.send(
        from_="billing@example.com", to="customer@example.com", subject="Invoice",
        attachment_ids=[uploaded.id],
    )

    assert result.id == "msg_123"
    upload_request = upload.calls.last.request
    assert upload_request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert upload_request.headers["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'filename="invoice.pdf"' in upload_request.content
    assert b"pdf" in upload_request.content
    assert json.loads(send.calls.last.request.content)["attachmentIds"] == ["att_123"]


@respx.mock
def test_send_sms(senviok: Senviok) -> None:
    route = respx.post(f"{BASE}/v1/sms").mock(return_value=httpx.Response(200, json={"id": "sms_1"}))
    result = senviok.sms.send(to="+2348012345678", from_="Senviok", text="Your code is 123456")
    assert result.id == "sms_1"
    body = json.loads(route.calls.last.request.content)
    assert body == {"to": "+2348012345678", "from": "Senviok", "text": "Your code is 123456"}


@respx.mock
def test_send_whatsapp(senviok: Senviok) -> None:
    route = respx.post(f"{BASE}/v1/whatsapp").mock(return_value=httpx.Response(200, json={"id": "wa_1"}))
    result = senviok.whatsapp.send(to="+2348012345678", from_="Senviok", text="Hello!")
    assert result.id == "wa_1"
    body = json.loads(route.calls.last.request.content)
    assert body == {"to": "+2348012345678", "from": "Senviok", "text": "Hello!"}


@respx.mock
def test_messages_list_uses_logs_wrapper_and_camel_case_params(senviok: Senviok) -> None:
    route = respx.get(f"{BASE}/v1/analytics/logs").mock(
        return_value=httpx.Response(
            200,
            json={
                "logs": [
                    {
                        "id": "log_1",
                        "channel": "email",
                        "status": "sent",
                        "toAddress": "dev@acme.com",
                        "fromAddress": "onboarding@acme.com",
                        "createdAt": "2026-07-01T10:00:00Z",
                    }
                ]
            },
        )
    )

    logs = senviok.messages.list(
        skip=5, take=10, channel="email", status="sent", to_address="dev@acme.com"
    )

    assert len(logs) == 1
    assert logs[0].id == "log_1"
    assert logs[0].channel == "email"
    assert logs[0].to_address == "dev@acme.com"
    params = route.calls.last.request.url.params
    assert params["skip"] == "5"
    assert params["take"] == "10"
    assert params["sortOrder"] == "desc"
    assert params["channel"] == "email"
    assert params["toAddress"] == "dev@acme.com"
    assert "subject" not in params  # unset filters are omitted


@respx.mock
def test_domains_full_flow(senviok: Senviok) -> None:
    respx.post(f"{BASE}/v1/domains").mock(
        return_value=httpx.Response(200, json={"id": "dom_1", "name": "example.com", "status": "pending"})
    )
    respx.get(f"{BASE}/v1/domains").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "dom_1", "name": "example.com", "status": "pending"}]}
        )
    )
    respx.get(f"{BASE}/v1/domains/dom_1/dkim").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "pending",
                "tokens": [
                    {"name": "dkim1", "value": "v=DKIM1; p=MIGf...", "type": "TXT", "status": True}
                ],
            },
        )
    )
    verify_route = respx.post(f"{BASE}/v1/domains/dom_1/verify").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "verified",
                "message": "Domain verified",
                "diagnostics": {"provider": "verified"},
            },
        )
    )

    created = senviok.domains.create(name="example.com")
    assert created.id == "dom_1"

    domains = senviok.domains.list()
    assert [d.name for d in domains] == ["example.com"]

    dkim = senviok.domains.get_dkim("dom_1")
    assert dkim.status == "pending"
    assert dkim.tokens[0].status is True

    verified = senviok.domains.verify("dom_1")
    assert verified.status == "verified"
    assert verified.diagnostics["provider"] == "verified"
    # verify() must be a POST with an empty body
    assert verify_route.calls.last.request.method == "POST"


@respx.mock
def test_webhooks_lifecycle_and_signature(senviok: Senviok) -> None:
    secret = "whsec_supersecret"
    respx.post(f"{BASE}/v1/webhooks").mock(
        return_value=httpx.Response(
            200, json={"id": "wh_1", "url": "https://app.example.com/hook", "secret": secret, "events": ["email.delivered"]}
        )
    )
    respx.get(f"{BASE}/v1/webhooks").mock(
        return_value=httpx.Response(
            200, json={"data": [{"id": "wh_1", "url": "https://app.example.com/hook", "secret": secret, "events": ["email.delivered"]}]}
        )
    )
    respx.get(f"{BASE}/v1/webhooks/wh_1/deliveries").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "dl_1", "webhookId": "wh_1", "eventType": "email.delivered", "attempt": 1, "statusCode": 200}]},
        )
    )
    respx.delete(f"{BASE}/v1/webhooks/wh_1").mock(return_value=httpx.Response(200, json={}))

    webhook = senviok.webhooks.create("https://app.example.com/hook", events=["email.delivered"])
    assert webhook.id == "wh_1"
    # single string events is normalized to a list
    created_body = json.loads(respx.calls.last.request.content)
    assert created_body["events"] == ["email.delivered"]

    assert [w.id for w in senviok.webhooks.list()] == ["wh_1"]
    deliveries = senviok.webhooks.logs("wh_1")
    assert deliveries[0].status_code == 200
    assert deliveries[0].webhook_id == "wh_1"

    raw = b'{"event":"email.delivered"}'
    import hashlib
    import hmac

    good = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert senviok.webhooks.verify_signature(raw, good, secret) is True
    assert senviok.webhooks.verify_signature(raw, "0" * 64, secret) is False
    assert senviok.webhooks.verify_signature(raw, "", secret) is False

    assert senviok.webhooks.delete("wh_1") is None


@respx.mock
def test_templates_bare_array_list(senviok: Senviok) -> None:
    respx.get(f"{BASE}/v1/templates").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "tpl_1", "name": "Welcome", "subject": "Hi", "htmlContent": "<p>Hi</p>"}],
        )
    )
    templates = senviok.templates.list()
    assert templates[0].name == "Welcome"
    assert templates[0].html_content == "<p>Hi</p>"


@respx.mock
def test_contacts_and_audiences(senviok: Senviok) -> None:
    respx.post(f"{BASE}/v1/audiences").mock(
        return_value=httpx.Response(200, json={"id": "aud_1", "name": "Beta", "createdAt": "2026-07-01T00:00:00Z"})
    )
    respx.post(f"{BASE}/v1/audiences/aud_1/contacts").mock(
        return_value=httpx.Response(
            200,
            json={"id": "con_1", "audienceId": "aud_1", "email": "dev@acme.com", "firstName": "Dev"},
        )
    )
    respx.get(f"{BASE}/v1/audiences/aud_1/contacts").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"id": "con_1", "audienceId": "aud_1", "email": "dev@acme.com", "firstName": "Dev"}]},
        )
    )

    audience = senviok.audiences.create(name="Beta")
    assert audience.id == "aud_1"

    contact = senviok.contacts.create("aud_1", email="dev@acme.com", first_name="Dev")
    assert contact.audience_id == "aud_1"
    body = json.loads(respx.calls.last.request.content)
    assert body == {"email": "dev@acme.com", "firstName": "Dev"}

    contacts = senviok.contacts.list("aud_1")
    assert contacts[0].first_name == "Dev"


@respx.mock
def test_api_keys_and_suppressions(senviok: Senviok) -> None:
    respx.post(f"{BASE}/v1/api-keys").mock(
        return_value=httpx.Response(
            200, json={"id": "key_1", "name": "prod", "token": "svk_live_abcdef", "createdAt": "2026-07-01T00:00:00Z"}
        )
    )
    respx.get(f"{BASE}/v1/api-keys").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "key_1", "name": "prod", "prefix": "svk_live"}]})
    )
    respx.post(f"{BASE}/v1/suppressions").mock(
        return_value=httpx.Response(200, json={"id": "sup_1", "email": "spam@example.com", "reason": "bounce"})
    )
    respx.get(f"{BASE}/v1/suppressions").mock(
        return_value=httpx.Response(200, json=[{"id": "sup_1", "email": "spam@example.com", "reason": "bounce"}])
    )

    created = senviok.api_keys.create(name="prod")
    assert created.token == "svk_live_abcdef"  # full token only returned on create
    assert senviok.api_keys.list()[0].prefix == "svk_live"

    suppression = senviok.suppressions.create("spam@example.com", reason="bounce")
    assert suppression.id == "sup_1"
    assert senviok.suppressions.list()[0].email == "spam@example.com"


@respx.mock
def test_error_mapping(senviok: Senviok) -> None:
    respx.post(f"{BASE}/v1/emails").mock(
        return_value=httpx.Response(401, json={"message": "Invalid API key"})
    )
    with pytest.raises(AuthenticationError, match="Invalid API key"):
        senviok.emails.send(from_="a@b.com", to="c@d.com", subject="x", html="<p>x</p>")

    respx.post(f"{BASE}/v1/sms").mock(
        return_value=httpx.Response(429, json={"message": "Rate limit exceeded"})
    )
    with pytest.raises(RateLimitError):
        senviok.sms.send(to="1", from_="2", text="3")

    respx.post(f"{BASE}/v1/whatsapp").mock(
        return_value=httpx.Response(500, json={"message": "Internal error"})
    )
    with pytest.raises(ApiError) as excinfo:
        senviok.whatsapp.send(to="1", from_="2", text="3")
    assert excinfo.value.status_code == 500


def test_requires_api_key() -> None:
    with pytest.raises(ValueError):
        Senviok(api_key="")  # type: ignore[arg-type]
