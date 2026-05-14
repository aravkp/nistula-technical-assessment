# Nistula — Guest Messaging Webhook

Technical assessment for the Nistula Summer Technology Internship 2026.

## Overview

A webhook that takes guest messages from WhatsApp, Booking.com, Airbnb,
Instagram and direct enquiries, drafts a reply with Claude against the
property's context, and routes each draft into one of three lanes —
`auto_send`, `agent_review`, or `escalate` — based on a confidence
score.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...

uvicorn app.main:app --reload
```

The server runs on `http://localhost:8000`. Interactive docs at
`http://localhost:8000/docs`.

## Testing

```bash
pytest
```

The webhook test suite mocks the Claude client, so tests run without
any API key and without network access.

To hit a running instance with the sample payloads:

```bash
bash sample_requests/curl_examples.sh
```

## Architecture

Request path for `POST /webhook/message`:

1. **Validate** — `app/schemas.py` Pydantic models reject malformed
   payloads with `422`.
2. **Normalise** — assign a `message_id` (UUID4), rename `message` →
   `message_text`.
3. **Classify** — `app/classifier.py` runs ordered keyword/regex rules
   over the message and returns one of six labels plus the matched
   keywords (for debugging and downstream features).
4. **Property context** — `app/property_context.py` formats the Villa B1
   data block that's injected into the Claude prompt.
5. **Draft** — `app/claude_client.py` calls Claude Sonnet 4 with a
   strict JSON-output system prompt and parses the response robustly
   (raw, ```json fences, or first `{…}` block).
6. **Score** — `app/confidence.py` blends three signals into a single
   `confidence_score`.
7. **Route** — thresholds map the score (and the query type) to an
   action.
8. **Respond** — fixed JSON shape: `message_id`, `query_type`,
   `drafted_reply`, `confidence_score`, `action`.

If the Claude call goes wrong — network, timeout, parse error, schema
mismatch — the wrapper catches it and hands back a degraded draft: a
generic acknowledgement, `confidence = 0.0`, and an `api_error` flag.
The webhook still answers `200`, so WhatsApp and the OTAs don't end up
retrying their way into a bigger outage.

## Confidence scoring logic

The composite score in `[0, 1]` is a weighted blend of three signals.

| Signal | Weight | Source |
| --- | --- | --- |
| `model_self_confidence` | 0.5 | Claude's own JSON output |
| `query_type_prior`      | 0.3 | Hand-set per query type |
| `uncertainty_penalty`   | 0.2 | `1 − 0.25 × len(flags)`, floored at 0 |

Priors per query type:

| Query type | Prior | Why |
| --- | --- | --- |
| `general_enquiry`        | 0.90 | Low-stakes, factual answers |
| `post_sales_checkin`     | 0.90 | Property context covers this well |
| `pre_sales_pricing`      | 0.85 | Rates are deterministic, dates may vary |
| `pre_sales_availability` | 0.80 | Needs a calendar check we don't yet do |
| `special_request`        | 0.60 | Usually requires a human to commit |
| `complaint`              | 0.20 | Never safe to auto-respond |

`uncertainty_flags` come back from Claude as short snake_case tokens
(e.g. `dates_unclear`, `missing_guest_count`). Each one shaves 0.25 off
the penalty term; four flags drag it to zero. Tuning rationale: a single
flag should soft-warn (still mostly fine), two flags should usually be
enough to drop out of auto-send for medium-prior queries.

**Hard complaint cap.** If `query_type == "complaint"`, the final score
is capped at `0.55`, which is below the `agent_review` threshold of
`0.60`. The router additionally forces `action = "escalate"` for
complaints regardless of the score. Two layers of belt-and-braces on
the same rule: we never want a Claude misfire to auto-send "no problem,
we'll refund you" to an angry guest.

The final score is clamped to `[0, 1]` and rounded to two decimals.

Action thresholds:

- `> 0.85` → `auto_send`
- `0.60 ≤ score ≤ 0.85` → `agent_review`
- `< 0.60` or `complaint` → `escalate`

## Design notes & assumptions

- **One property in scope.** Only Villa B1 was in scope, so the context
  lives inline in `property_context.py`. In production it would be a
  row in the `properties` table defined in `schema.sql`.
- **No persistence layer.** The webhook is stateless — nothing writes
  to a database. `schema.sql` shows where messages, conversations,
  reservations and guest identities would land if it did.
- **Classifier is rule-based, on purpose.** Six classes with strong
  keyword signal don't need a model — rules are faster, easier to
  debug, and have no training-data dependency. The
  `classifier_version = "rules-v1"` stamp lets us re-classify history
  whenever the rules change.
- **Single `messages` table.** Inbound and outbound on every channel
  share one table, with the role-specific columns nullable. The
  reasoning lives in `schema.sql`'s "hardest design decision" stub —
  I left that paragraph for you to write, but the schema is shaped to
  back it up.
- **Guest identity unification.** A `guests` row is a person; a
  `guest_identities` row is one of their handles on one channel. The
  split keeps "who they are" separate from "where to reach them".
- **`reservation_id` is nullable on `conversations`.** Pre-sales
  enquiries arrive before any booking exists, so the link has to be
  optional.

## What I'd do with more time

- Persistence wiring — the schema exists, the writes don't.
- Retry with jittered backoff on transient Claude errors before giving
  up to the degraded reply.
- Per-source rate limiting so one noisy WhatsApp number can't burn
  through the token budget on its own.
- An eval set of ~200 labelled real messages and a CI job that fails
  when classifier accuracy regresses.
- Multi-turn context so Claude sees the last 5–10 exchanges, not just
  the latest message.
- A real availability check against the `reservations` table for
  pre-sales queries — right now Claude has to hedge.
- Outbound delivery: actually post the auto-replies back through the
  channel APIs and persist them as outbound rows in `messages`.
