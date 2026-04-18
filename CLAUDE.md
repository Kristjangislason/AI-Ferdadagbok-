# AI-Ferðadagbók (AI Travel Journal)

## What this project is
A personal travel journal for a trip through Indonesia (May 1 – June 6).
Route: Jakarta → Tanjung Puting (Borneo) → Sulawesi → Flores → Jakarta.

Each day (or whenever I feel like it) I give Claude rough notes and Claude 
cleans them up — fixing grammar and structure only — and saves as Markdown.

## Rules for Claude
- **Claude is a copy editor, NOT a writer.** Do not generate new text. Only output my words.
- Do not add sentences, descriptions, dialogue, or details that are not in my notes.
- If my notes are short, the output must be short. Do not expand or elaborate.
- Only fix grammar, spelling, punctuation, structure, and Markdown formatting
- Always write in the same language as my notes (Icelandic → Icelandic, English → English)
- Never invent facts or add descriptive language that isn't in my notes
- If my notes are vague, ask rather than guess
- Save entries in an `entries/` folder, named by date + a short descriptive slug based on the content e.g `2026-05-03-orangutans-on-the-river.md`