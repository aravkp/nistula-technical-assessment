# Part 3 — Thinking Question

## Question A — The Immediate Response

**The message:**

Hi [name], I'm so sorry — that's not the stay we promised, and I know the timing with your breakfast guests makes this urgent. I'm reaching our caretaker now to get someone to you as fast as possible. I'll update you within 20 minutes, and we'll make this right.

**Why this wording:** At 3am the guest needs to feel a human is moving — not a form reply, not a bot-grade promise. One action, one timeline, acknowledgement of the breakfast-guest stakes, no refund — that's a human call, which is why complaints escalate rather than auto-resolve.

## Question B — The System Design

When the classifier flags a complaint, the system escalates immediately — the confidence cap skips agent_review:

- Open a complaint ticket linked to the conversation, guest, and reservation so whoever picks it up has full context.
- Page on-call staff (push, call, SMS — not a quiet dashboard ping). The caretaker goes first since they're nearest.
- Log everything — inbound message, AI draft, score, query type, timestamp, and the fact it was escalated. Audit trail and Question C's input.
- Start a 30-minute timer. No acknowledgement and it escalates again, manager or founder-level, while the guest gets an automated follow-up so they aren't left silent past the 20-minute promise.
- Refunds stay with humans. Staff can offer compensation when they take the ticket; the system surfaces the option and logs the outcome but never auto-issues money.

The AI buys time; the system guarantees a human shows up.

## Question C — The Learning

A single complaint is a ticket. A pattern is a different signal — the goal shifts from fixing this guest's problem to stopping the problem from existing.

- Detect it. Every complaint is logged with property ID, theme, and timestamp, so a rolling-window check on same-property/same-theme trips a property-level alert. Three hot-water hits at Villa B1 in two months raises the flag.
- Route it to whoever owns the property — maintenance, not on-call — as an assigned task, separate from the guest tickets.
- Surface it on a per-property dashboard. The root cause of the third complaint isn't the heater; it's that nobody connected the three tickets.

To stop a fourth: the rolling-window detector (cheap — it runs on data already stored), a maintenance-task system so the alert becomes an owned, tracked job, and a pre-emptive inspection before the next guest arrives.

The system should learn from its own logs.
