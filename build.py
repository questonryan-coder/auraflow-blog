#!/usr/bin/env python3
"""AuraFlow Blog — zero-dependency static site builder.

Reads posts/*.md (simple front matter + a small markdown subset) and renders:
  index.html, <slug>/index.html, sitemap.xml, robots.txt, feed.xml,
  and the IndexNow key files. Output goes to the repo root so GitHub Pages
  can serve it directly from the main branch.
"""
import html
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from email.utils import format_datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(ROOT, "posts")
BASE = "https://questonryan-coder.github.io/auraflow-blog"
SITE_NAME = "AuraFlow Blog"
SITE_DESC = "Notes on sleep sounds, focus, and sound that never loops — from AuraFlow, the live-generated soundscape app at auraflowfocus.com."
APP_URL = "https://auraflowfocus.com"

CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0a0a12; color: #d8d8e2; font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.65; }
a { color: #9db8ff; }
a:hover { color: #c3d4ff; }
.wrap { max-width: 44rem; margin: 0 auto; padding: 1.25rem 1.1rem 3rem; }
header.site { display: flex; justify-content: space-between; align-items: baseline; padding: 0.6rem 0 1.2rem; border-bottom: 1px solid #23233a; margin-bottom: 1.8rem; }
header.site .brand { font-weight: 700; font-size: 1.15rem; color: #f0f0f8; text-decoration: none; }
header.site nav a { margin-left: 1rem; font-size: 0.95rem; text-decoration: none; }
h1 { color: #f4f4fa; font-size: 1.9rem; line-height: 1.25; margin: 0.4rem 0 0.8rem; }
h2 { color: #ececf6; font-size: 1.35rem; margin: 2rem 0 0.6rem; }
h3 { color: #e2e2ee; font-size: 1.1rem; margin: 1.5rem 0 0.4rem; }
p { margin: 0.7rem 0; }
ul, ol { margin: 0.7rem 0; padding-left: 1.4rem; }
li { margin: 0.3rem 0; }
blockquote { margin: 1rem 0; padding: 0.6rem 1rem; border-left: 3px solid #3d4a7a; background: #10101e; color: #c6c6d6; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.95rem; }
th, td { border: 1px solid #2a2a44; padding: 0.45rem 0.6rem; text-align: left; }
th { background: #14142a; color: #f0f0f8; }
.meta { color: #8b8ba3; font-size: 0.9rem; }
.postlist { list-style: none; padding: 0; }
.postlist li { margin: 0 0 1.4rem; }
.postlist a.title { font-size: 1.2rem; font-weight: 600; color: #eef; text-decoration: none; }
.postlist a.title:hover { text-decoration: underline; }
.postlist p { margin: 0.25rem 0; color: #b9b9cc; }
.cta { margin-top: 2.6rem; padding: 1.3rem 1.2rem; background: #11112a; border: 1px solid #2c2c50; border-radius: 10px; }
.cta h2 { margin-top: 0; }
.cta .btn { display: inline-block; margin: 0.5rem 0 0.8rem; padding: 0.55rem 1.1rem; background: #3d5afe; color: #fff; border-radius: 6px; text-decoration: none; font-weight: 600; }
.cta .btn:hover { background: #5876ff; color: #fff; }
.cta .related { font-size: 0.95rem; color: #a9a9c2; }
footer.site { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #23233a; color: #8b8ba3; font-size: 0.9rem; }
"""

# ----------------------------------------------------------------------------
# Front matter + markdown subset
# ----------------------------------------------------------------------------

def parse_post(path):
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---"):
        raise ValueError(f"{path}: missing front matter")
    _, fm, body = text.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["related"] = [s.strip() for s in meta.get("related", "").split(",") if s.strip()]
    meta["body"] = body.strip()
    return meta


def inline(text):
    """Inline markdown: links, bold, italic, code. Input is raw text."""
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def plain(text):
    """Strip inline markdown markers for schema/plain-text use."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("**", "").replace("*", "").replace("`", "").strip()


def render_markdown(body):
    lines = body.splitlines()
    out = []
    i = 0
    n = len(lines)

    def is_block_start(line):
        return bool(re.match(r"^(#{1,6}\s|[-*]\s|\d+\.\s|>\s|>\s*$|\|)", line))

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            out.append(f"<h{level}>{inline(m.group(2).strip())}</h{level}>")
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < n and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            if len(cells) >= 2 and all(set(c) <= set("-: ") for c in cells[1]):
                head, body_rows = cells[0], cells[2:]
            else:
                head, body_rows = cells[0], cells[1:]
            thead = "".join(f"<th>{inline(c)}</th>" for c in head)
            trs = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body_rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{trs}</tbody></table>")
            continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>" + render_markdown("\n".join(buf)) + "</blockquote>")
            continue
        if re.match(r"^[-*]\s", line):
            items = []
            while i < n and re.match(r"^[-*]\s", lines[i]):
                items.append(re.sub(r"^[-*]\s", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s", line):
            items = []
            while i < n and re.match(r"^\d+\.\s", lines[i]):
                items.append(re.sub(r"^\d+\.\s", "", lines[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        # paragraph: gather until blank line or next block start
        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


def extract_faq(body):
    """Return [(question, answer)] from a '## FAQ' section (### = question)."""
    faqs = []
    in_faq = False
    q = None
    ans = []
    for line in body.splitlines():
        m2 = re.match(r"^##\s+(.*)$", line)
        m3 = re.match(r"^###\s+(.*)$", line)
        if m2:
            if in_faq and q:
                faqs.append((q, " ".join(ans).strip()))
                q, ans = None, []
            in_faq = m2.group(1).strip().lower().startswith("faq")
            continue
        if in_faq and m3:
            if q:
                faqs.append((q, " ".join(ans).strip()))
            q = plain(m3.group(1))
            ans = []
            continue
        if in_faq and q and line.strip():
            ans.append(plain(line))
    if in_faq and q:
        faqs.append((q, " ".join(ans).strip()))
    return [(q, a) for q, a in faqs if q and a]


# ----------------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------------

def layout(title, description, canonical, body_html, extra_head=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME}" href="{BASE}/feed.xml">
<style>{CSS}</style>
{extra_head}</head>
<body>
<div class="wrap">
<header class="site">
<a class="brand" href="{BASE}/">{SITE_NAME}</a>
<nav><a href="{BASE}/">All posts</a><a href="{APP_URL}">AuraFlow app</a></nav>
</header>
<main>
{body_html}
</main>
<footer class="site">
<p>From <a href="{APP_URL}">AuraFlow</a> — sound worlds generated live in your browser. Type anything, hear it built. Free to try, no account.</p>
</footer>
</div>
</body>
</html>
"""


def post_page(post, by_slug):
    slug = post["slug"]
    url = f"{BASE}/{slug}/"
    article = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": post["title"],
        "description": post["description"],
        "datePublished": post["date"],
        "dateModified": post["date"],
        "author": {"@type": "Organization", "name": "AuraFlow", "url": APP_URL},
        "publisher": {"@type": "Organization", "name": "AuraFlow", "url": APP_URL},
        "mainEntityOfPage": url,
    }
    schemas = [article]
    faqs = extract_faq(post["body"])
    if faqs:
        schemas.append({
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q,
                 "acceptedAnswer": {"@type": "Answer", "text": a}}
                for q, a in faqs
            ],
        })
    extra = "".join(
        f'<script type="application/ld+json">\n{json.dumps(s, indent=2)}\n</script>\n'
        for s in schemas
    )
    related_links = []
    for rslug in post["related"]:
        if rslug in by_slug:
            related_links.append(
                f'<a href="../{rslug}/">{html.escape(by_slug[rslug]["title"])}</a>'
            )
    related_html = ""
    if related_links:
        related_html = ('<p class="related">Keep reading: ' + " · ".join(related_links) + "</p>")
    cta = f"""
<section class="cta">
<h2>Try it — free, no account</h2>
<p>Type anything at AuraFlow and it builds that sound world live — rain over the ocean, a quiet forest, brown noise, whatever you name. Your first world is free to keep, and you can take a 60-second taste of the rest. Pro is $9/month or $79/year, with a 7-day free trial on the monthly plan.</p>
<a class="btn" href="{APP_URL}">Open AuraFlow — free to try</a>
{related_html}
</section>"""
    body_html = (
        f'<p class="meta">{post["date"]} · <a href="{BASE}/">AuraFlow Blog</a></p>\n'
        + render_markdown(post["body"])
        + cta
    )
    return layout(post["title"], post["description"], url, body_html, extra)


def index_page(posts):
    items = []
    for p in posts:
        items.append(
            f'<li><a class="title" href="{p["slug"]}/">{html.escape(p["title"])}</a>'
            f'<p class="meta">{p["date"]}</p><p>{html.escape(p["description"])}</p></li>'
        )
    body_html = f"""<h1>{SITE_NAME}</h1>
<p>{html.escape(SITE_DESC)}</p>
<ul class="postlist">
{''.join(items)}
</ul>
<section class="cta">
<h2>Sound that never loops</h2>
<p>AuraFlow generates every soundscape live in your browser — no recordings, no loop points. Type anything and hear it built.</p>
<a class="btn" href="{APP_URL}">Open AuraFlow — free to try</a>
</section>"""
    return layout(SITE_NAME, SITE_DESC, f"{BASE}/", body_html)


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------

def main():
    posts = []
    for name in sorted(os.listdir(POSTS_DIR)):
        if name.endswith(".md"):
            posts.append(parse_post(os.path.join(POSTS_DIR, name)))
    posts.sort(key=lambda p: (p["date"], p["title"]), reverse=True)
    by_slug = {p["slug"]: p for p in posts}

    for p in posts:
        outdir = os.path.join(ROOT, p["slug"])
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
            f.write(post_page(p, by_slug))
        print(f"built {p['slug']}/index.html")

    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_page(posts))
    print("built index.html")

    urls = [f"{BASE}/"] + [f"{BASE}/{p['slug']}/" for p in posts]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in posts:
        sm.append(f"  <url><loc>{BASE}/{p['slug']}/</loc><lastmod>{p['date']}</lastmod></url>")
    sm.append(f"  <url><loc>{BASE}/</loc><lastmod>{posts[0]['date']}</lastmod></url>")
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(sm) + "\n")

    with open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")

    items = []
    for p in posts:
        dt = datetime.strptime(p["date"], "%Y-%m-%d").replace(
            hour=12, tzinfo=timezone.utc)
        items.append(
            "    <item>\n"
            f"      <title>{html.escape(p['title'])}</title>\n"
            f"      <link>{BASE}/{p['slug']}/</link>\n"
            f"      <guid>{BASE}/{p['slug']}/</guid>\n"
            f"      <pubDate>{format_datetime(dt)}</pubDate>\n"
            f"      <description>{html.escape(p['description'])}</description>\n"
            "    </item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"  <title>{SITE_NAME}</title>\n"
        f"  <link>{BASE}/</link>\n"
        f"  <description>{html.escape(SITE_DESC)}</description>\n"
        + "\n".join(items)
        + "\n</channel></rss>\n"
    )
    with open(os.path.join(ROOT, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(feed)

    # IndexNow key — reuse if present so the published key file stays valid.
    key = None
    keyfile = os.path.join(ROOT, "indexnow-key.txt")
    if os.path.exists(keyfile):
        key = open(keyfile, encoding="utf-8").read().strip()
    if not key:
        key = secrets.token_hex(16)
        with open(keyfile, "w", encoding="utf-8") as f:
            f.write(key + "\n")
    with open(os.path.join(ROOT, f"{key}.txt"), "w", encoding="utf-8") as f:
        f.write(key)
    with open(os.path.join(ROOT, "INDEXNOW_KEY.txt"), "w", encoding="utf-8") as f:
        f.write(key + "\n")

    print(f"posts: {len(posts)}  indexnow key: {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
