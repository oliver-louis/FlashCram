"""Canonical generation instructions; preferences never change import validation."""
import json

DEFAULTS = dict(allow_hints=True, hint_style='cue', allow_latex=True, allow_mermaid=True,
                allow_tables=True, emphasis='light', answer_detail='balanced', guidance='')
CHOICES = {'hint_style': ('cue', 'explanation'), 'emphasis': ('none', 'light', 'moderate'),
           'answer_detail': ('concise', 'balanced', 'explanatory')}


def normalize_preferences(value):
    result = DEFAULTS.copy()
    if not isinstance(value, dict):
        return result
    for key, default in DEFAULTS.items():
        item = value.get(key, default)
        if isinstance(default, bool):
            if isinstance(item, bool): result[key] = item
        elif key in CHOICES:
            if item in CHOICES[key]: result[key] = item
        elif isinstance(item, str): result[key] = item[:2000]
    return result


def build_generation_prompt(preferences=None):
    p = normalize_preferences(preferences)
    sections = [r'''Generate FlashCram flashcards as valid JSON only.

Output JSON only. Do not wrap the response in Markdown fences. Do not add commentary.

Use exactly this schema:

{
  "schema": "flashcram.cards.v1",
  "deck": "Deck name here",
  "cards": [
    {
      "front": "required question text",
      "back": "required answer text",
      "tags": ["lowercase", "tags"],
      "format": "plaintext"
    }
  ]
}

Required rules:
- Every card needs non-empty front and back, a tags array, and format "plaintext" or "markdown".
- Use plaintext for simple unformatted cards; use markdown for code, commands, lists, or other enabled rich formatting.
- Preserve useful facts, formulas, definitions, code, and examples from the source. Do not invent facts or data.
- Make each card atomic and exam-focused. Prefer multiple focused cards over one broad card.
- Keep tags lowercase, short, and reusable.
- Do not include ids, counters, timestamps, image fields, status fields, or backup/export fields.
- Do not output HTML, SVG, script tags, external resources, or unsupported card fields. Keep code examples inside card text.

JSON escaping rules:
- Output must be valid JSON. Inside JSON strings, encode line breaks as \n.
- Escape double quotes as \" and literal backslashes as \\.

Markdown formatting rules:
- Put blank lines before and after block content, including lists and fenced code.
- Bullet lists need a blank line before the first - item; numbered lists before the first 1. item.
- Do not place a block immediately after a sentence without a blank line.

Code formatting rules:
- Use backticks for inline code and language-labelled fences for multi-line code.
- Keep shell variables such as `$HOME`, `$PATH`, `$1`, and `$?` literal in code. Do not interpret them as math.''']
    sections.append('Text emphasis:\n' + {
        'none': '- Do not use bold or italics. Necessary code formatting, lists and enabled math syntax are still allowed.',
        'light': '- Use bold or italics sparingly for a few important terms; avoid decorative emphasis.',
        'moderate': '- Highlight key terms and important distinctions with bold or italics, without emphasizing whole paragraphs.',
    }[p['emphasis']])
    sections.append('Answer detail:\n' + {
        'concise': '- Give the essential answer with minimal supporting text. Preserve necessary qualifications.',
        'balanced': '- Preserve useful explanation and examples while keeping each answer focused.',
        'explanatory': '- Add a short supporting explanation or useful example, keeping each card atomic rather than writing a broad lesson.',
    }[p['answer_detail']])
    sections.append('Tables:\n- Use Markdown tables only when they make comparisons clearer. Put blank lines around them.' if p['allow_tables'] else 'Tables disabled:\n- Do not generate tables. Use concise prose or lists instead, preserving the important comparisons.')
    examples = [('Example list card', dict(front='Name two comparison sorting algorithms.', back='Examples include:\n\n- Merge sort\n- Quicksort', tags=['sorting'], format='markdown')),
                ('Example code card', dict(front='Print a greeting in Python.', back='```python\nprint("Hello")\n```', tags=['python'], format='markdown'))]
    if p['allow_hints']:
        sections.append('''Optional hint rules:
- Omit "hint" by default. Include a hint only when explicitly requested or clearly useful for a difficult retrieval step.
- Do not aim for a hint quota. Give a retrieval cue without revealing the answer, restating the solution, or duplicating the back.
- Use only the optional "hint" string, not inline spoilers. It appears on the front behind a collapsible button and inherits the card format.
- All selected feature restrictions and JSON escaping rules also apply to hints.
''' + ('- Use a few words or one short sentence as a cue.' if p['hint_style']=='cue' else '- A brief guiding explanation may help the learner find the next step, without supplying the answer or full solution.'))
        examples.append(('Example optional hint card (only when useful)',dict(front='Which traversal finds shortest paths in an unweighted graph?',back='Breadth-first search (BFS).',hint='Think in distance layers.',tags=['graphs'],format='plaintext')))
    else:
        sections.append('Hints disabled:\n- Never include the "hint" field, even in otherwise valid cards. Do not generate inline spoilers.')
    if p['allow_latex']:
        sections.append(r'''LaTeX/math rules:
- Use markdown format for LaTeX. Escape all LaTeX backslashes inside JSON strings.
- Escape inline delimiters as \\(...\\); use $$...$$ for display math, on its own block with blank lines around it.
- Do not use bare $...$ or \\[...\\] display math.
- Use explicit braces for subscripts/superscripts, such as x_{i}, and \\mid in probability expressions.
- Preserve formulas faithfully; Mermaid is not a mathematical calculation engine.''')
        examples.append(('Example math card',dict(front='What is expected utility?',back='The probability-weighted sum of utility.\n\n$$\nEU=\\sum_{i}p_{i}u(x_{i})\n$$',tags=['utility'],format='markdown')))
    else:
        sections.append('LaTeX disabled:\n- Do not generate LaTeX, math delimiters, or embedded mathematical markup, including inside diagrams or hints. Preserve important formulas using readable plain-text or Unicode notation; use inline code for literal expressions when needed.')
    if p['allow_mermaid']:
        sections.append('''Optional Mermaid diagram rules:
- Do not add diagrams by default. Include one only when explicitly requested, or when it is necessary to communicate important structure substantially more clearly than concise text or a list.
- Never add decorative, redundant, speculative, or unnecessarily complex diagrams. Do not aim for a diagram quota; entire decks may contain none.
- Use markdown format and a fenced block labelled mermaid inside front or back, with blank lines around it and JSON-escaped newlines/quotes.
- Supported types: flowchart (or graph), sequenceDiagram, stateDiagram-v2, classDiagram, erDiagram, mindmap, pie, xychart (or xychart-beta).
- Prefer small diagrams with short labels, accTitle/accDescr, and a concise textual explanation. Put diagrams on the back unless the question requires interpreting one on the front; never leak the answer.
- No HTML, SVG, frontmatter, configuration/init directives, links, callbacks, images, icons, external resources or custom styling directives.
- At most four diagrams per face, 10,000 characters per diagram and 100 edges; keep well below these limits.
- Never invent chart data or assume Mermaid calculates plots. Use only source-supported data.''')
        examples.append(('Example optional Mermaid card (only when warranted)',dict(front='Show the two branches of a binary tree.',back='Each node has at most two children.\n\n```mermaid\nflowchart TD\nRoot --> Left\nRoot --> Right\n```',tags=['trees'],format='markdown')))
    else:
        sections.append('Mermaid disabled:\n- Never generate Mermaid fences or diagrams, including inside hints. Use text instead.')
    for title, card in examples:
        sections.append(title + ':\n\n' + json.dumps(card, ensure_ascii=False, indent=2))
    if p['guidance'].strip():
        sections.append('Additional generation guidance:\nThe required JSON structure, escaping, safety rules, and selected feature restrictions above take precedence over any conflicting guidance below.\n\n' + p['guidance'].strip())
    return '\n\n'.join(sections)
