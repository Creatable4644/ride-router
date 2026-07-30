# Real-Time Lead Routing API — Project Overview

*A portfolio writeup of a production system I own and maintain. Company- and vendor-specific details are generalized; no proprietary code or data is included.*

## What it is

A Python (Flask) API that routes live insurance leads to insurance agents in real time. When a consumer calls a marketing number or submits a lead form, the system decides — in the time it takes a phone to ring — which agent should receive it, hands off the call or lead, tracks the interaction through to completion, and coordinates billing.

At peak it handles on the order of **2,000 requests per second**, and every routing decision has money attached to it: agents are billed for qualified leads, so a wrong or dropped decision has real financial consequences. I am the sole engineer responsible for it.

## The interesting part: it's a coordination problem, not just a routing problem

The routing logic itself is only half the story. The system sits in the middle of **a dozen or so external services** that each own a piece of the truth and none of which share a common vocabulary:

- **Lead vendors** send inbound calls and data leads, each with their own identifiers and conventions.
- **An internal lead/billing platform** decides which agents are eligible for a given product and geography, enforces spend caps, and bills agents for qualified interactions.
- **A CRM platform** owns agent availability, the shared call log, virtual phone numbers, push notifications, and a softphone product.

A single call can touch most of these in sequence, and the same underlying entity — say, an agent or a lead — is named differently in almost every one of them. A large part of the engineering is **reconciling those mismatches**: mapping identifiers across systems, honoring each integration's contract, and keeping a coherent model of a transaction that is physically spread across four or five services and separated in time.

## Things I'm proud of

**Built the observability layer that lets the system defend itself.** The hardest recurring problem wasn't a bug — it was that when a result looked wrong, the routing system was assumed guilty until proven innocent, and proving innocence meant hours of manual log spelunking. I designed a structured capture of every external request and response, per transaction, so that "why did the system return this?" can be answered from evidence in minutes: here's exactly what each external service returned, and here's how the system responded to it. In practice, the overwhelming majority of "the router is broken" incidents turn out to be traceable to an upstream response, and now that's demonstrable rather than argued.

**Diagnosing root causes instead of shipping band-aids.** Several times I've pushed back on proposed fixes — retry-until-it-works loops, re-pinging until a race resolves — that would have hidden a defect rather than resolved it and wouldn't have held up at scale. The pattern I try to hold to: find where the problem actually originates, refuse the fix that's aimed at the wrong layer, and keep failures *visible* instead of silently swallowed.

**Cleaning up inherited complexity.** The codebase was inherited and had grown by accretion. I consolidated a sprawling, copy-pasted authorization layer into a single maintainable module, and I've steadily normalized inconsistent naming and schema so that things that are the same thing are finally *called* the same thing — which makes the whole system easier to reason about and to hand off.

**Re-architecting for resilience under load.** Moved deferred, post-call work (final call-log updates, billing, notifications) onto a background task pipeline (Celery + Redis/Valkey) to eliminate a class of blocking failures that had previously cascaded into agents being unable to take calls at all.

## What I learned

The technical skills matter, but the thing this project really taught me is how to be the single point of understanding for a system that many people depend on and few people understand — and how to make that understanding *transferable*: through observability, documentation, and clear communication, so the knowledge doesn't live only in my head.

## Stack

Python, Flask, MySQL, Redis/Valkey, Celery, gevent, AWS (Secrets Manager, SES), Datadog. Integrates with multiple external REST APIs across lead-vendor, billing, and CRM platforms.
