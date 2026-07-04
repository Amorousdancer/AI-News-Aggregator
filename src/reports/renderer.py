"""Markdown to HTML rendering for daily reports."""

from __future__ import annotations

import markdown_it


def markdown_to_html(markdown_text: str) -> str:
    """Render markdown to HTML with a clean, readable style."""
    md = markdown_it.MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": True})

    body = md.render(markdown_text)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily News Report</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem 1rem;
    line-height: 1.6;
    color: #1a1a1a;
  }}
  h1 {{ font-size: 1.8rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }}
  h2 {{ font-size: 1.3rem; margin-top: 2rem; color: #333; }}
  h3 {{ font-size: 1.1rem; }}
  a {{ color: #0066cc; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 0; padding-left: 1rem; color: #555; }}
  code {{ background: #f4f4f4; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f4f4f4; padding: 1rem; border-radius: 5px; overflow-x: auto; }}
  img {{ max-width: 100%; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
  th {{ background: #f8f8f8; }}
  ul, ol {{ padding-left: 1.5rem; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
