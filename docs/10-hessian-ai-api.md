# hessian.AI Inference API

Source: the hessian.AI "Inference API" handout given to each team (26.10.2026).

| Item | Value |
|---|---|
| Base URL | `https://hip-gw.hessian.ai/v1` |
| Route | `POST /chat/completions` (OpenAI-compatible) |
| Auth | `Authorization: Bearer <team key>` |
| Models | `vllm/Kolibri-1` (Aleph Alpha, text, DE/EN, tool calling) · `vllm/GLM-Flash:Latest` (Z.ai, text + vision) |
| Context | 512K tokens (both) |
| Access until | Wed 28.10.2026, 09:00 (UTC+1) |

> **The team key is secret.** The handout says: one key per team, do not share it outside the team.
> It must **never** be committed to this public repo, written into the demo HTML, or put into a
> published artifact. In the demo, paste it into **⚙ AI settings**; it is stored only in your
> browser's `localStorage`.

## Example

```bash
export HAI_API_KEY="<your team key>"
curl https://hip-gw.hessian.ai/v1/chat/completions \
  -H "Authorization: Bearer $HAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "vllm/Kolibri-1", "messages": [{"role": "user", "content": "Hallo"}]}'
```

## How the demo uses it

The live mode sends **one spec section** (plus its directly linked cross-references) and a
`tools` schema (`extract_rule_parameters`). The model must answer with a tool call containing:

- `function_id`: which pre-written rule function the clause maps to,
- `params`: the numbers it found (e.g. `six_months: 6`, `min_days: 30`),
- `quotes`: for each parameter, the **verbatim** German sentence it came from.

The answer then goes through the deterministic guards (quote exists verbatim in the spec, the
number appears in the quote, the schema and range are valid, run A = run B). Only then can an
examiner approve it. The model never computes expected values. See [09-demo-design.md](09-demo-design.md).

If the call fails (network, CORS, no tool-call support), the demo falls back to its recorded
outputs and says so on screen.
