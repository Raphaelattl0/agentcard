# AgentCard.dev — Marketing content pack

Two phases:
- **Phase 1 — Build in public (NOW):** create curiosity + a waitlist. No production promises.
- **Phase 2 — Big launch (AFTER auth + persistent storage are done):** "it's live, use it."

You publish everything yourself. I draft; you approve and post.
Live URL: https://agentcard-dev.onrender.com · Repo: https://github.com/Raphaelattl0/agentcard

---

## PHASE 1 — BUILD IN PUBLIC (use now)

### X / Twitter — thread (post now)

**1/**
I'm building something this week: drop in your OpenAPI spec, and it instantly becomes
both an MCP server (that Claude can use) AND a signed A2A agent.

One API. Both protocols. No infra to run.

Building in public 🧵

**2/**
The problem: every company has a REST API. To make an AI actually *use* it, someone has
to hand-write an MCP server or an A2A wrapper. It's boring plumbing nobody wants to write.

So I'm turning that plumbing into a single POST request.

**3/**
You give it:
- an OpenAPI spec (or a few endpoints by hand)

You get back:
- a hosted MCP endpoint any MCP client can connect to
- a cryptographically signed A2A Agent Card
- same engine behind both

**4/**
Already working: imported the Swagger Petstore spec (13 paths) → 19 MCP tools generated
automatically, live, callable. No code written by me beyond the spec.

**5/**
Why both protocols? MCP is what Claude & IDEs use *today*. A2A is the agent-to-agent
future. Most tools make you pick. Here you provision once and get both.

**6/**
Next up: per-tenant auth + persistent storage, then a public launch.

If you have an API you'd want an AI to call, reply or DM — I'm looking for 5 early testers.
Follow along for the launch.

---

### LinkedIn — post (post now)

I've been building a small tool and I want to share the idea early.

Every company has a REST API. But for an AI assistant like Claude to actually *use* that
API, someone has to write an "MCP server" or an "A2A agent" wrapper around it — repetitive
integration plumbing.

My tool removes that step: you give it your OpenAPI spec, and it instantly hosts both an
MCP server (usable by Claude and other AI clients today) and a signed A2A agent (for
agent-to-agent), from a single request. Same engine, both outputs.

It's early — I'm building in public and looking for a handful of people with an API who'd
like an AI to call it. If that's you, let's talk.

#MCP #AI #Agents #API #BuildInPublic

---

### Reddit r/mcp — teaser post (post now)

**Title:** Building a service that turns any OpenAPI spec into a hosted MCP server (+ A2A) — looking for early testers

**Body:**
I got tired of hand-writing MCP servers to wrap existing REST APIs, so I'm building a
service that does it from an OpenAPI spec: POST the spec, get a hosted MCP endpoint with
tools auto-generated from each operation. As a bonus it also emits a signed A2A agent card
from the same engine.

Already working end-to-end (imported the Petstore spec → 19 MCP tools, callable live).
Still early — adding per-tenant auth and persistent storage before a real launch.

Looking for ~5 people with an API who'd like to try wrapping it. Happy to do it with you.
Feedback on the approach very welcome.

---

## PHASE 2 — BIG LAUNCH (use after auth + storage are done)

### Hacker News — Show HN

**Title:** Show HN: Turn your OpenAPI spec into a hosted MCP server and A2A agent

**Body:**
Hi HN. AgentCard takes an OpenAPI spec (or a few manually described endpoints) and gives
you two things from one request: a hosted MCP server that Claude and other MCP clients can
connect to, and a cryptographically signed A2A Agent Card — backed by the same execution
engine.

Each API operation becomes both an MCP tool and an A2A skill. When a client calls a tool,
we make the real upstream HTTP call and stream the result back. Multi-tenant, ES256-signed
cards.

I built it because wrapping an existing REST API for AI use is repetitive plumbing, and
most tools make you choose MCP *or* A2A. Here you provision once and get both.

Live demo + docs: https://agentcard-dev.onrender.com
Tech: FastAPI, OpenAPI→tool conversion, JSON-RPC for both façades.

Would love feedback on the conversion quality and the dual-protocol approach.

### X / Twitter — launch thread (later)

**1/** It's live. Turn any API into an MCP server Claude can use — in one request. 🚀
(then reuse points 2-5 from Phase 1, present tense + "try it now: <url>")

### LinkedIn — launch post (later)
Same as Phase 1 LinkedIn but: "It's live — try it" + link + a 30-sec demo video/GIF of
Claude connecting to a generated MCP server and calling a tool.

---

## DISTRIBUTION CHANNELS (often beats social posts)

Submit the MCP server / product to MCP directories and registries — free, targeted reach:
- modelcontextprotocol.io ecosystem / official servers list
- mcp.so
- "Awesome MCP Servers" GitHub lists (open a PR)
- Glama MCP directory
- Smithery (smithery.ai) MCP registry
- Product Hunt (for the launch day)

Also: write one short "how it works" blog post / dev.to article and link it from every post.

---

## THE "WOW" DEMO (record this — it sells better than any copy)

30-second screen recording:
1. Paste an OpenAPI spec → provision.
2. Add the returned MCP URL to an MCP client (Claude).
3. Ask Claude to use one of the auto-generated tools → it calls the real API live.

Caption: "From OpenAPI spec to a tool Claude can call — no code, ~60 seconds."
This single clip is the most reusable asset across every channel.
