"""Safe, source-preserving Mermaid fences; no diagram execution on the server."""
import html
import re

TYPES = {'flowchart', 'graph', 'sequenceDiagram', 'stateDiagram', 'stateDiagram-v2',
         'classDiagram', 'erDiagram', 'mindmap', 'pie', 'xychart', 'xychart-beta'}
PROHIBITED = re.compile(r'%%\{|(?:^|;)\s*(?:---|click\b|style\b|classDef\b|class\s|linkStyle\b|[a-z]+Style\b)|https?://|<\s*[/!a-z]|@\{|\b(?:icon|image)\s*:', re.I | re.M)


def diagram_error(source):
    if len(source) > 10_000:
        return 'Diagram exceeds the 10,000 character limit.'
    meaningful = [line.strip() for line in source.splitlines() if line.strip() and not line.strip().startswith('%%')]
    if not meaningful or meaningful[0].split()[0] not in TYPES:
        return 'Unsupported diagram type.'
    if PROHIBITED.search(source):
        return 'Diagram configuration, HTML, links, images, and custom styling are not supported.'
    return ''


def mermaid_fence(source, language, class_name, options, md, **kwargs):
    count = getattr(md, 'flashcram_diagrams', 0) + 1
    md.flashcram_diagrams = count
    error = 'A card face supports at most four diagrams.' if count > 4 else diagram_error(source)
    # Source stays in a code element: escaped, never interpreted as HTML or math.
    status = f'<p role="status">{html.escape(error)}</p>' if error else '<p role="status">Loading diagram…</p>'
    return (f'<div class="fc-diagram" data-mermaid="{"error" if error else "pending"}" data-no-swipe="true">'
            f'{status}<pre><code>{html.escape(source)}</code></pre></div>')


def summary_fence(source, language, class_name, options, md, **kwargs):
    return '<p>Diagram</p>'
