# Senviok Python SDK

Official Python client for the [Senviok](https://senviok.live) messaging API —
email, SMS and WhatsApp, plus the resources around them. Mirrors the official
JavaScript SDK's public facade 1:1, so the two stay in lockstep.

- Sync (`Senviok`) and async (`AsyncSenviok`) clients
- Typed request and response models (pydantic)
- Automatic camelCase serialization — the API's quirks are handled for you
  (e.g. list endpoints that return bare arrays vs. wrapped payloads)
- `webhooks.verify_signature()` for validating webhook payloads

## Installation

```bash
pip install senviok
```

## Quick start

```python
from senviok import Senviok

senviok = Senviok("svk_live_xxx")

# Email — note `from_` (trailing underscore: `from` is a Python keyword)
message = senviok.emails.send(
    from_="Acme <onboarding@acme.com>",
    to="dev@acme.com",                      # or a list: ["dev@acme.com", "ops@acme.com"]
    subject="Hello from Senviok",
    html="<p>Hello!</p>",
)
print(message.id)  # msg_...

# SMS
senviok.sms.send(to="+2348012345678", from_="Senviok", text="Your code is 123456")

# WhatsApp
senviok.whatsapp.send(to="+2348012345678", from_="Senviok", text="Hello!")
```

## Resources

| Resource | Methods |
| --- | --- |
| `emails` | `send(...)` |
| `sms` | `send(to, from_, text)` |
| `whatsapp` | `send(to, from_, text)` |
| `messages` | `list(skip, take, sort_order, channel, status, to_address, from_address, subject, start_date, end_date)` |
| `webhooks` | `create(url, events)`, `list()`, `delete(id)`, `logs(webhook_id)`, `verify_signature(raw_body, signature, secret)` |
| `templates` | `create(name, subject, html_content)`, `list()`, `get(id)`, `update(id, ...)`, `delete(id)` |
| `domains` | `create(name)`, `list()`, `get_dkim(id)`, `verify(id)` |
| `audiences` | `create(name)`, `list()`, `delete(id)` |
| `contacts` | `create(audience_id, email, first_name, last_name, unsubscribed)`, `list(audience_id)`, `delete(audience_id, id)` |
| `suppressions` | `create(email, reason)`, `list()`, `delete(id)` |
| `api_keys` | `create(name)`, `list()`, `delete(id)` |

### Email options

`emails.send` accepts the same options as the JS SDK, with snake_case names:

- `from_`, `from_name`, `to`, `subject`, `html`, `text`
- `cc`, `bcc`, `reply_to`
- `template_id`, `template_data`
- `add_unsubscribe_footer`, `add_list_unsubscribe_header`

Unknown options raise `TypeError` immediately — no silent typos.

### Webhook signature verification

```python
raw_body = b'{"event":"email.delivered","messageId":"msg_123"}'

if senviok.webhooks.verify_signature(raw_body, signature, secret):
    # signature is valid — process the event
    ...
```

## Async usage

```python
import asyncio
from senviok import AsyncSenviok

async def main():
    async with AsyncSenviok("svk_live_xxx") as senviok:
        await senviok.emails.send(
            from_="hi@example.com",
            to="user@example.com",
            subject="Hi",
            html="<p>Hi</p>",
        )
        logs = await senviok.messages.list(take=10)

asyncio.run(main())
```

## Local development

Point the client at a locally running API:

```python
senviok = Senviok("dev-key", base_url="http://localhost:5033")
```

## Errors

| Exception | When |
| --- | --- |
| `AuthenticationError` | Missing/invalid API key (HTTP 401/403) |
| `RateLimitError` | Tenant rate limit exceeded (HTTP 429, 100 req/min) |
| `ApiError` | Any other non-2xx response (carries `status_code` and raw `body`) |

All inherit from `SenviokError`.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## License

MIT
