# Provider And Protocol Routing

## Decision Order

1. If Hermes already has a native provider for the official platform, use it.
2. Otherwise inspect the platform's current API documentation.
3. If it implements OpenAI Chat Completions, use the helper's automated path.
4. If it implements Anthropic Messages or another native protocol, configure
   only the Hermes-native path or build a Provider adapter.
5. Do not configure Tavern unless the endpoint exposes a compatible Chat
   Completions route.

An endpoint is not OpenAI-compatible merely because it accepts a bearer token or
uses `/v1`. Confirm its request and response schema.

## Required OpenAI-Compatible Surface

- `POST <base>/chat/completions`
- `messages` with `system`, `user`, and `assistant` roles
- non-streaming JSON response containing assistant content
- a valid model ID

The agent probe additionally requires tool/function calling. Tavern does not.
`GET <base>/models` is useful but optional because some gateways omit it.

## Provider Adapter Boundary

Build a Hermes Provider adapter when the API requires native authentication,
request signing, OAuth refresh, a non-OpenAI message schema, or provider-specific
stream decoding. A Skill may orchestrate that adapter, but must not emulate a
new wire protocol with undocumented request rewriting.

Vendor documentation is authoritative for `api_mode`, base URL, model ID,
extra request fields, context window, and output-token limits.

