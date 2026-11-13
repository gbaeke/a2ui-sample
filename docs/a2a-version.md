# A2A version: why this sample is on A2A 0.3

Decided on 2026-11-13: the sample stays on A2A 0.3 for now. This note records why, and what a move
to A2A 1.0 would involve.

## What is in use

| Side | Package | Version | A2A protocol |
| --- | --- | --- | --- |
| Agent (Python) | `a2a-sdk` | 0.3.26 | 0.3 |
| Middleware (Node) | `@a2a-js/sdk` | 0.3.14 | 0.3 |

The A2UI payload inside the A2A messages is A2UI 1.0. Only the transport is on the older version.

## Why not A2A 1.0

A2A 1.0 has been available since April 2026 (`a2a-sdk` 1.0.0 on 2026-04-20; 1.3.0 is current).
The A2UI project has not moved to it:

- `a2ui-a2a` 0.3.0, A2UI's Python helper for A2A, declares `a2a-sdk>=0.3.0,<0.4.0`. Installing it
  is what pulled in A2A SDK 0.3.
- The unreleased `a2ui-a2a` in the A2UI repository has the same pin (checked on 2026-11-13).
- Every reference sample in the A2UI repository, Python and JavaScript, uses the 0.3 line
  (`@a2a-js/sdk ^0.3.13` on the JavaScript side).

Staying on 0.3 keeps the sample on the combination the A2UI project itself tests.

## What depends on the A2A version

Only two places:

- `agent/hours_agent/executor.py` and `agent/hours_agent/__main__.py` (A2A server, task updates,
  agent card).
- `web/middleware/a2a.ts` (A2A client).

The browser code, the catalog and the agent's reply logic do not: the browser only talks to the
middleware's `/a2a` endpoint.

## Moving to A2A 1.0 later

1. Check whether `a2ui-a2a` has dropped the `<0.4.0` pin. If it has, upgrade both SDKs and adapt
   the two places above to the 1.x APIs.
2. If it has not, drop `a2ui-a2a` and replace the three things used from it:
   - `create_a2ui_part`: wraps an A2UI message in an A2A data part with
     `metadata.mimeType = "application/a2ui+json"`.
   - `get_a2ui_messages`: reads the A2UI data parts from an inbound A2A message.
   - `get_a2ui_agent_extension` and `try_activate_a2ui_extension`: the agent-card entry for
     `https://a2ui.org/a2a-extension/a2ui/v1.0` and its activation from the `X-A2A-Extensions`
     header.
3. Move `@a2a-js/sdk` to 1.x in `web/` and adapt the middleware.

Not tried yet: nothing in this repository has been run against the 1.x SDKs.

## Related difference

`a2ui-a2a` 0.3.0 puts one A2UI message in each A2A data part. The A2UI 1.0 extension specification
says a data part holds a list of messages. The agent accepts both on input; the middleware and
browser accept both on output.
