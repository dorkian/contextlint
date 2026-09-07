---
name: alpha
description: Use when the user asks to summarise a changelog into release notes.
---
# Alpha

Read the changelog file, group entries by change type, and write release notes.

Rules:
- Keep the summary under 200 words.
- Preserve issue and PR references verbatim; never renumber them.
- Put breaking changes first, under their own heading, regardless of date order.
- If an entry has no type prefix, infer one from the verb and mark it as inferred.
- Never invent an entry that is not present in the source changelog.
