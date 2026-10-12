---
name: short-nice-response
description: Write the final response to the user as short bullet points in simple-english, at most 250 words. Use when asked for a short, nice, brief, or scannable response or answer (e.g. "/short-nice-response", "give me a short nice response").
---

# Short nice response

Shape the final response to the user so it reads in one glance. This skill
controls only the response text — do the task itself as usual first.

## Write with simple-english

Invoke the `simple-english` skill in pragmatic mode before drafting the
response, and keep it on for the whole response. It owns the sentence:
20/25-word limits, one word one meaning, simple tenses, active voice, no
filler. This skill owns the length and the structure; where they disagree,
this one wins. Code, commands, identifiers, and file paths are untouchable
in both skills.

## Rules

- **Hard cap: 250 words** for the entire final response. Count them; if
  over, cut detail, not clarity. Code blocks count toward the cap.
- **Short bullet points.** One idea per bullet, one sentence where
  possible. At most one lead-in sentence before the bullets. No
  paragraph-form explanations.
- Put the answer or outcome first, then the supporting bullets.
- Keep `file_path:line_number` references, failures, and open questions —
  cut background and restatement of the request before those.
