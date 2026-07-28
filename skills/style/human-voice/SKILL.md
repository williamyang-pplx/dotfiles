---
name: human-voice
description: Rewrite prose so it reads like a person wrote it, not a model — plain words, simple sentences, no fancy punctuation (no semicolons, colons, or dashes). Use when asked to write or clean up prose, docs, messages, or comments in a human voice. Prose-only — never touches code logic.
---

# Write in a human voice

Make the text sound like a real person typed it in one sitting. The goal is
plain, direct writing that never gives away a model wrote it.

## Scope

- Applies to prose: docs, comments, commit bodies, messages, READMEs, PR text.
- If the request names a file or block, rewrite that. Otherwise rewrite the
  text the user just gave you.
- Never change code behavior, APIs, or logic. Only the words.

## Punctuation

- No semicolons. Split into two sentences instead.
- No colons to join clauses. Start a new sentence. Colons are fine only to
  introduce a real list.
- No dashes of any kind for asides or emphasis. Not em dashes, not en dashes,
  not " - ". Use a comma, a period, or parentheses.
- Cut fancy marks. No ellipses for effect, no arrows, no fancy quotes. Use plain
  quotes and periods.
- Commas are fine, but do not stack three or four into one sentence. If you
  need that many, the sentence should be two sentences.

## Sentences

- One idea per sentence. If a sentence has two ideas, break it in two.
- Keep sentences short. Aim under 20 words. A few longer ones are fine, but
  they should be rare.
- No nested clauses. Avoid "which", "wherein", and stacked "that" clauses.
- Prefer the active voice. "The script fails" beats "failures are produced by
  the script".
- Vary the length a little. All-short reads robotic too. Mostly short with the
  occasional medium sentence sounds human.

## Words

- Use common words. "use" not "utilize", "help" not "facilitate", "start" not
  "commence", "about" not "regarding".
- Cut filler openers: "It is worth noting that", "In order to", "Additionally",
  "Furthermore", "It should be mentioned". Say the thing.
- Drop hedge stacks like "it seems that it may possibly". Say what you mean.
- No throat-clearing conclusions like "In summary" or "Overall". Just end.
- Avoid the model tells: "delve", "leverage", "robust", "seamless", "elevate",
  "unlock", "in today's world", "at the end of the day".
- Contractions are good. "don't", "it's", "you'll" read as human.

## What to keep

- Keep the meaning exact. Do not drop facts to sound simpler.
- Keep technical terms that are the real name for something. Plain does not mean
  vague.
- Keep the author's intent and any strong claims. This is a voice pass, not a
  softening pass.

## After rewriting

- Read it back once. If a sentence would be hard to say out loud in one breath,
  split it.
- Scan for any semicolon, colon, or dash you missed and fix it.
- Show the rewritten text. If asked, note what you changed and why in a line or
  two.
