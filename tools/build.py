#!/usr/bin/env python3
"""Build the static site from content/ into the repository root.

  content/profile.json    name, bio, career, principles
  content/papers.json     research papers (PDFs live in papers/)
  content/writing.json    every article; LinkedIn ones have a slug and a body
  content/articles/*.html article bodies produced by tools/import_linkedin.py
  content/projects.json   projects page
  content/lab.json        lab page

Usage: python3 tools/build.py
Preview: python3 -m http.server 8000   then open http://localhost:8000
"""
import json
import re
import subprocess
from datetime import date
from html import escape
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE_URL = "https://yakovshkolnikov.com"
NAV = [("Home", "/"), ("Research", "/research/"), ("Writing", "/writing/"), ("Projects", "/projects/"),
       ("Lab", "/lab/"), ("About", "/about/")]
TOPICS = ["Trust & Safety", "Agents in Practice", "Work & Economics", "Research Notes",
          "Using AI Well", "Fiction", "Lab Notes"]


def load(name):
    return json.loads((CONTENT / f"{name}.json").read_text())


profile, papers, writing = load("profile"), load("papers"), load("writing")
projects, lab, pubs = load("projects"), load("lab"), load("publications")
by_slug = {w["slug"]: w for w in writing if w.get("slug")}
links_by = {l["label"]: l["url"] for l in profile["links"]}
local_by_source = {w["source"].rstrip("/"): f"/writing/{w['slug']}/" for w in writing if w.get("slug")}


# ---------- helpers ----------

def e(s):
    return escape(s or "", quote=True)


def fmt_date(d, short=False):
    parts = d.split("-")
    y, m = int(parts[0]), int(parts[1])
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    mon = months[m - 1][:3] if short else months[m - 1]
    return f"{mon} {int(parts[2])}, {y}" if len(parts) == 3 else f"{mon} {y}"


def href(w):
    return f"/writing/{w['slug']}/" if w.get("slug") else w["source"]


def is_local(w):
    return bool(w.get("slug"))


def link(url, text, cls=""):
    ext = url.startswith("http")
    attrs = f' class="{cls}{" " if cls else ""}ext"' if ext else (f' class="{cls}"' if cls else "")
    rel = ' rel="noopener"' if ext else ""
    return f'<a href="{e(url)}"{attrs}{rel}>{text}</a>'


def pic_of(w):
    """Full-size hero for a writing entry: the archived LinkedIn cover or a fetched og:image."""
    if w.get("cover"):
        return {**w["cover"], "src": f'/writing/{w["slug"]}/{w["cover"]["src"]}'}
    return w.get("image")


def thumb(pic, width=640):
    """Return a resized copy of a site image, generating it on first use."""
    src = ROOT / pic["src"].lstrip("/")
    out = src.with_name(f"{src.stem}-{width}.webp")
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        im = Image.open(src).convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(out, "WEBP", quality=80, method=6)
    with Image.open(out) as im:
        w, h = im.size
    return {"src": "/" + str(out.relative_to(ROOT)), "width": w, "height": h}


def img_tag(pic, cls="", alt="", width=640, eager=False, vt=None):
    t = thumb(pic, width) if width else pic
    style = f' style="view-transition-name: {vt}"' if vt else ""
    return (f'<img{" class=\"" + cls + "\"" if cls else ""} src="{t["src"]}" alt="{e(alt)}" '
            f'width="{t["width"]}" height="{t["height"]}"{"" if eager else " loading=\"lazy\""}{style}>')


def vt_name(w):
    """Shared view-transition name so a list image glides into the article hero."""
    return f"hero-{w['slug']}" if w.get("slug") else None


def paper_thumb(p):
    """First page of the paper's PDF as an image, rendered with pdftoppm."""
    out = ROOT / "papers" / "thumbs" / f"{p['id']}.webp"
    pdf = ROOT / "papers" / p["pdf"]
    if not out.exists() or out.stat().st_mtime < pdf.stat().st_mtime:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix("")
        subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-r", "90", "-png", "-singlefile", str(pdf), str(tmp)], check=True, stderr=subprocess.DEVNULL)
        png = tmp.with_suffix(".png")
        im = Image.open(png).convert("RGB")
        im = im.resize((520, round(im.height * 520 / im.width)), Image.LANCZOS)
        im.save(out, "WEBP", quality=80, method=6)
        png.unlink()
    with Image.open(out) as im:
        w, h = im.size
    return {"src": f"/papers/thumbs/{p['id']}.webp", "width": w, "height": h}


def reading_time(words):
    return f"{max(1, round(words / 230))} min read"


def page(path, title, body, *, description, active=None, og_image=None, og_type="website",
         head_extra="", scripts=""):
    url = SITE_URL + path
    full_title = title if title == profile["name"] else f"{title} · {profile['name']}"
    nav = "".join(
        f'<a href="{u}"{" aria-current=\"page\"" if label == active else ""}>{label}</a>'
        for label, u in NAV)
    foot_links = "".join(f'<a href="{e(l["url"])}" rel="noopener">{e(l["label"])}</a>'
                         for l in profile["links"])
    og = f'<meta property="og:image" content="{SITE_URL}{og_image}">' if og_image else ""
    card = "summary_large_image" if og_image else "summary"
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
<meta name="author" content="{e(profile['name'])}">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="{e(profile['name'])}: Writing" href="/feed.xml">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#7f1d1d">
<meta property="og:site_name" content="{e(profile['name'])}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{url}">
{og}
<meta name="twitter:card" content="{card}">
<script>try{{var t=localStorage.getItem("theme");if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
<link rel="preload" href="/assets/fonts/source-serif-4-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/site.css">
{head_extra}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header"><div class="wrap">
<a class="site-name" href="/">{e(profile['name'])}</a>
<div class="header-right">
<nav class="site-nav" aria-label="Main">{nav}</nav>
<button class="theme-toggle" type="button" hidden aria-label="Switch colour theme"></button>
</div>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-footer"><div class="wrap">
<span>&copy; {date.today().year} {e(profile['name'])}<span class="sep">·</span>Updated {fmt_date(date.today().isoformat())}</span>
<nav aria-label="Elsewhere">{foot_links}<a href="/employment_july_2026.html">Employment Calculator</a><a href="/feed.xml">RSS</a></nav>
</div></footer>
{scripts}
<script>
(function(){{
  var b=document.querySelector('.theme-toggle'), root=document.documentElement;
  var sys=window.matchMedia('(prefers-color-scheme: dark)');
  function cur(){{return root.dataset.theme||(sys.matches?'dark':'light');}}
  function label(){{
    var next=cur()==='dark'?'Light':'Dark';
    b.innerHTML=(next==='Dark'
      ?'<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M6 1a7 7 0 1 0 9 9A6 6 0 0 1 6 1z"/></svg>'
      :'<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.2" fill="currentColor"/><g stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M8 .8v2M8 13.2v2M.8 8h2M13.2 8h2M2.9 2.9l1.4 1.4M11.7 11.7l1.4 1.4M2.9 13.1l1.4-1.4M11.7 4.3l1.4-1.4"/></g></svg>')+next;
    b.setAttribute('aria-label','Switch to '+next.toLowerCase()+' theme');
  }}
  b.hidden=false; label();
  b.addEventListener('click',function(){{
    var t=cur()==='dark'?'light':'dark'; root.dataset.theme=t;
    try{{localStorage.setItem('theme',t);}}catch(e){{}}
    label();
  }});
  sys.addEventListener('change',label);
}})();
</script>
</body>
</html>
"""
    html = re.sub(r"\n{2,}", "\n", html)
    out = ROOT / path.lstrip("/")
    if path.endswith("/"):
        out = out / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return path


def jsonld(obj):
    return f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'


def writing_meta(w, short=True):
    bits = [f'<time datetime="{w["date"]}">{fmt_date(w["date"], short)}</time>']
    bits.append(e(w["venue"]) if not is_local(w) else "LinkedIn")
    if w.get("words") and is_local(w):
        bits.append(reading_time(w["words"]))
    return '<span class="sep">·</span>'.join(bits)


def paper_links(p, related=True):
    out = [f'<a href="/papers/{p["pdf"]}">PDF</a>',
           link(p["url"], "arXiv" if p["venue"].startswith("arXiv") else "SSRN")]
    if p.get("code"):
        out.append(link(p["code"], p.get("code_label", "Code")))
    if p.get("archive"):
        out.append(link(p["archive"]["url"], p["archive"]["label"]))
    if related:
        for s in p.get("related", []):
            if s in by_slug:
                out.append(f'<span class="related">Essay: <a href="/writing/{s}/">{e(by_slug[s]["title"])}</a></span>')
    return f'<div class="links-row">{"".join(out)}</div>'


def bibtex(p):
    year = p["date"][:4]
    key = f"shkolnikov{year}{re.sub(r'[^a-z]', '', p['id'].split('-')[0])}"
    if p["venue"].startswith("arXiv"):
        num = p["venue"].split(":")[1]
        return (f"@misc{{{key},\n  title         = {{{p['title']}}},\n  author        = {{Shkolnikov, Yakov P.}},\n"
                f"  year          = {{{year}}},\n  eprint        = {{{num}}},\n  archivePrefix = {{arXiv}},\n"
                f"  url           = {{{p['url']}}}\n}}")
    return (f"@techreport{{{key},\n  title       = {{{p['title']}}},\n  author      = {{Shkolnikov, Yakov P.}},\n"
            f"  year        = {{{year}}},\n  institution = {{SSRN}},\n  type        = {{Working paper}},\n"
            f"  number      = {{{p['venue'].split()[-1]}}},\n  url         = {{{p['url']}}}\n}}")


def writing_item(w, show_thumb=True):
    t = f'<a href="{e(href(w))}"{"" if is_local(w) else " class=\"ext\" rel=\"noopener\""}>{e(w["title"])}</a>'
    img = ""
    pic = pic_of(w)
    if show_thumb and pic:
        img = f'<a class="thumb-link" href="{e(href(w))}" tabindex="-1" aria-hidden="true">{img_tag(pic, "thumb", width=480, vt=vt_name(w))}</a>'
    cls = "entry has-thumb" if img else "entry"
    return (f'<li data-topic="{e(w.get("topic", ""))}"><div class="{cls}"><div>'
            f'<h3>{t}</h3><div class="meta">{writing_meta(w)}<span class="sep">·</span>{e(w.get("topic", ""))}</div>'
            f'<p class="desc">{e(w["description"])}.</p></div>{img}</div></li>')


# ---------- pages ----------

def build_home():
    links = "".join(link(l["url"], e(l["label"])) for l in profile["links"])
    with_pics = [w for w in writing if pic_of(w)]
    lead, rest = with_pics[0], with_pics[1:7]

    def title_link(w):
        return f'<a href="{e(href(w))}"{"" if is_local(w) else " class=\"ext\" rel=\"noopener\""}>{e(w["title"])}</a>'

    lead_html = f"""<article class="lead">
<a class="lead-img thumb-link" href="{e(href(lead))}" tabindex="-1" aria-hidden="true">{img_tag(pic_of(lead), width=1100, eager=True, vt=vt_name(lead))}</a>
<div class="lead-text">
<p class="kicker">Latest writing</p>
<h2>{title_link(lead)}</h2>
<p class="meta">{writing_meta(lead, short=False)}</p>
<p class="desc">{e(lead['description'])}.</p>
</div>
</article>"""
    tiles = "".join(
        f'<li><a class="thumb-link" href="{e(href(w))}" tabindex="-1" aria-hidden="true">{img_tag(pic_of(w), width=640, vt=vt_name(w))}</a>'
        f'<h3>{title_link(w)}</h3><p class="meta">{writing_meta(w)}</p></li>'
        for w in rest)
    paper_tiles = "".join(
        f'<li><a class="page-thumb thumb-link" href="/research/#{p["id"]}" tabindex="-1" aria-hidden="true">{img_tag(paper_thumb(p), width=0)}</a>'
        f'<h3><a href="/research/#{p["id"]}">{e(p["title"])}</a></h3>'
        f'<p class="meta">{e(p["venue"])}<span class="sep">·</span>{fmt_date(p["date"], True)}</p>'
        f'<p class="meta"><a href="/papers/{p["pdf"]}">PDF</a></p></li>'
        for p in papers[:4])
    body = f"""
<section class="intro">
<h1>{e(profile['name'])}</h1>
<p class="creds">{e(profile['headline'])}</p>
<p>{e(profile['intro'])}</p>
<p class="summary">{e(profile['bio'][1].split('. ')[0])}. <a href="/about/">About me</a>.</p>
<div class="links">{links}</div>
</section>
{lead_html}
<h2 class="section">More writing <a class="more" href="/writing/">All {len(writing)} pieces</a></h2>
<ul class="tiles">{tiles}</ul>
<h2 class="section">Recent papers <a class="more" href="/research/">All research and publications</a></h2>
<ul class="tiles papers-row">{paper_tiles}</ul>
"""
    person = {
        "@context": "https://schema.org", "@type": "Person", "name": profile["name"], "url": SITE_URL,
        "jobTitle": "Founder, Soundness AI",
        "sameAs": [l["url"] for l in profile["links"]],
        "alumniOf": [{"@type": "CollegeOrUniversity", "name": "Princeton University"},
                     {"@type": "CollegeOrUniversity", "name": "Cornell University"}],
        "knowsAbout": ["Artificial Intelligence", "AI Safety", "Agentic AI", "Edge Inference",
                       "Medical Devices", "Signal Processing"],
    }
    # the old single-page site used #tab anchors; send those visitors to the new pages
    legacy = ("<script>(function(){var m={writing:'/writing/',research:'/research/',systems:'/projects/',"
              "safety:'/projects/',career:'/about/',philosophy:'/about/#principles',lab:'/lab/'};"
              "var h=location.hash.slice(1);if(m[h])location.replace(m[h]);})();</script>")
    page("/", profile["name"], body, head_extra=jsonld(person), scripts=legacy, active="Home",
         og_image=thumb(pic_of(lead), 1200)["src"],
         description=f"{profile['name']}: {profile['headline']}. Research and writing on AI trust, agents, "
                     "and production AI systems. " + profile["credentials"] + ".")


PUB_GROUPS = [("journal", "Journal articles"), ("conference", "Conference papers"),
              ("thesis", "Doctoral thesis"), ("patent", "Patent")]


def pub_item(x):
    authors = e(x["authors"]).replace("YP Shkolnikov", "<strong>YP Shkolnikov</strong>").replace(
        "Y Shkolnikov", "<strong>Y Shkolnikov</strong>")
    cites = f'<span class="sep">·</span>cited by {x["cites"]}' if x["cites"] else ""
    return (f'<li>{authors}. {link(x["scholar"], e(x["title"]))}. <em>{e(x["venue"])}</em>, {x["year"]}'
            f'<span class="meta">{cites}</span></li>')


def publications_html():
    out = []
    for kind, label in PUB_GROUPS:
        xs = [x for x in pubs if x["kind"] == kind]
        if xs:
            out.append(f'<h3 class="sub">{label} ({len(xs)})</h3><ol class="pubs">{"".join(pub_item(x) for x in xs)}</ol>')
    xs = [x for x in pubs if x["kind"] == "abstract"]
    out.append(f'<details class="more-pubs"><summary>Conference abstracts, letters, and preprints ({len(xs)})</summary>'
               f'<ol class="pubs">{"".join(pub_item(x) for x in xs)}</ol></details>')
    return "".join(out)


def build_research():
    items = []
    for p in papers:
        items.append(f"""<li class="paper" id="{p['id']}"><div class="paper-row">
<a class="page-thumb thumb-link" href="/papers/{p['pdf']}" tabindex="-1" aria-hidden="true">{img_tag(paper_thumb(p), width=0)}</a>
<div>
<h3><a href="/papers/{p['pdf']}">{e(p['title'])}</a></h3>
<div class="meta">{e(profile['name'])}<span class="sep">·</span>{e(p['kind'])}, {e(p['venue'])}<span class="sep">·</span>{fmt_date(p['date'])}<span class="sep">·</span>{p['pages']} pages</div>
<p class="summary">{e(p['summary'])}</p>
{paper_links(p)}
<details class="cite"><summary>Cite</summary><pre>{e(bibtex(p))}</pre></details>
</div></div></li>""")
    software = [i for g in projects["groups"] if g["title"] == "Open source" for i in g["items"] if i.get("url")]
    sw = "".join(item_dl(i) for i in software)
    body = f"""
<div class="page-head">
<h1>Research</h1>
<p>{e(profile['pages']['research'])}</p>
</div>
<h2 class="section">Preprints and working papers, 2026</h2>
<ul class="list">{''.join(items)}</ul>
<h2 class="section" id="publications">Publications, 2002&ndash;2013</h2>
<p class="prose">{e(profile['scholar'])} Citation counts are from {link('https://scholar.google.com/citations?user=zTtAbu4AAAAJ&hl=en', 'Google Scholar')}.</p>
{publications_html()}
<h2 class="section">Research software</h2>
<dl class="items">{sw}</dl>
"""
    scholarly = [{"@context": "https://schema.org", "@type": "ScholarlyArticle", "headline": p["title"],
                  "author": {"@type": "Person", "name": profile["name"]}, "datePublished": p["date"],
                  "url": p["url"], "encoding": {"@type": "MediaObject", "contentUrl": f"{SITE_URL}/papers/{p['pdf']}",
                                                "encodingFormat": "application/pdf"}} for p in papers]
    page("/research/", "Research", body, active="Research", head_extra=jsonld(scholarly),
         og_image=paper_thumb(papers[0])["src"],
         description="Preprints and working papers by Yakov Shkolnikov on AI trust boundaries, deception, "
                     "persistent agents, efficient architectures, and AI economics, with PDFs.")


def build_writing_index():
    used = [t for t in TOPICS if any(w.get("topic") == t for w in writing)]
    sep = '<span class="sep">·</span>'
    buttons = "Show: " + sep.join(
        [f'<button type="button" aria-pressed="true" data-topic="">All</button>'] +
        [f'<button type="button" aria-pressed="false" data-topic="{e(t)}">{e(t)}</button>' for t in used])
    years, blocks = [], []
    for w in writing:
        y = w["date"][:4]
        if not years or years[-1] != y:
            if years:
                blocks.append("</ul>")
            years.append(y)
            blocks.append(f'<h2 class="year">{y}</h2><ul class="list">')
        blocks.append(writing_item(w))
    blocks.append("</ul>")
    body = f"""
<div class="page-head">
<h1>Writing</h1>
<p>{e(profile['pages']['writing'])}</p>
<p style="margin-top:.8rem">{e(profile['pages']['newsletter'])} {link(links_by['Substack'], 'Subscribe')}</p>
</div>
<div class="filters" role="group" aria-label="Filter by topic" hidden>{buttons}</div>
{''.join(blocks)}
"""
    script = """<script>
(function(){
  var bar=document.querySelector('.filters'); bar.hidden=false;
  var btns=bar.querySelectorAll('button'), items=document.querySelectorAll('li[data-topic]');
  function apply(t){
    btns.forEach(function(b){b.setAttribute('aria-pressed', b.dataset.topic===t?'true':'false');});
    items.forEach(function(li){li.hidden = t && li.dataset.topic!==t;});
    document.querySelectorAll('.year').forEach(function(h){
      var ul=h.nextElementSibling; h.hidden = ul.hidden = !ul.querySelector('li:not([hidden])');
    });
  }
  bar.addEventListener('click',function(ev){
    var b=ev.target.closest('button'); if(!b) return;
    apply(b.dataset.topic); history.replaceState(null,'',b.dataset.topic?'#'+encodeURIComponent(b.dataset.topic):location.pathname);
  });
  var h=decodeURIComponent(location.hash.slice(1)); if(h) apply(h);
})();
</script>"""
    page("/writing/", "Writing", body, active="Writing", scripts=script,
         og_image=thumb(pic_of(next(w for w in writing if pic_of(w))), 1200)["src"],
         description="Essays by Yakov Shkolnikov on AI trust, agents, evaluation, and the economics of AI at work.")


def rewrite_links(html):
    def sub(m):
        url = m.group(1)
        local = local_by_source.get(url.split("?")[0].rstrip("/"))
        return f'href="{local}"' if local else f'href="{url}"'
    html = re.sub(r'href="([^"]+)"', sub, html)
    # Markdown-style links pasted into the LinkedIn editor: "[<a href=..>label](url)</a>"
    html = re.sub(r'\[(<a href="[^"]+">)([^<\]]+)\]\([^)<]+\)(</a>)', r"\1\2\3", html)
    # LinkedIn articles often start at h3; promote so headings follow the page h1
    if "<h2>" not in html:
        html = html.replace("<h3>", "<h2>").replace("</h3>", "</h2>")
    # lists pasted inside a paragraph
    html = re.sub(r"<p>\s*(<(ul|ol)>.*?</\2>)\s*</p>", r"\1", html, flags=re.S)
    return html


def build_articles():
    local = [w for w in writing if is_local(w)]
    papers_by_slug = {}
    for p in papers:
        for s in p.get("related", []):
            papers_by_slug.setdefault(s, []).append(p)
    for i, w in enumerate(local):
        body_html = rewrite_links((CONTENT / "articles" / f"{w['slug']}.html").read_text())
        cover = ""
        if w.get("cover"):  # full-size hero on the article itself
            c = w["cover"]
            cap = f"<figcaption>{e(c['alt'])}</figcaption>" if c.get("alt") else ""
            cover = (f'<figure class="cover"><img src="{c["src"]}" alt="{e(c.get("alt", ""))}" '
                     f'width="{c["width"]}" height="{c["height"]}" style="view-transition-name: {vt_name(w)}">{cap}</figure>')
        rel = "".join(
            f'<p>Related paper: <a href="/research/#{p["id"]}">{e(p["title"])}</a> '
            f'<span class="meta">({e(p["kind"]).lower()}, {e(p["venue"])}; <a href="/papers/{p["pdf"]}">PDF</a>)</span></p>'
            for p in papers_by_slug.get(w["slug"], []))
        newer = local[i - 1] if i > 0 else None
        older = local[i + 1] if i + 1 < len(local) else None
        pager = '<nav class="pager" aria-label="More writing">'
        pager += (f'<a href="/writing/{older["slug"]}/"><small>Previous</small>{e(older["title"])}</a>'
                  if older else "<span></span>")
        pager += (f'<a class="next" href="/writing/{newer["slug"]}/"><small>Next</small>{e(newer["title"])}</a>'
                  if newer else "<span></span>")
        pager += "</nav>"
        topic = f'<span class="sep">·</span>{e(w["topic"])}' if w.get("topic") else ""
        body = f"""
<article>
<header class="article-head">
<a class="crumb" href="/writing/">&larr; Writing</a>
<h1>{e(w['title'])}</h1>
<div class="meta"><time datetime="{w['date']}">{fmt_date(w['date'])}</time><span class="sep">·</span>{reading_time(w['words'])}{topic}</div>
<p class="origin">Originally published on LinkedIn. {link(w['source'], 'Read the original')}</p>
</header>
{cover}
<div class="article-body">
{body_html}
</div>
<footer class="article-foot">
<p class="meta">This copy is archived from {link(w['source'], 'LinkedIn')}, where the original remains the published version.</p>
{rel}
{pager}
</footer>
</article>
"""
        og = f"/writing/{w['slug']}/{w['cover']['src']}" if w.get("cover") else None
        ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": w["title"],
              "datePublished": w["date"], "author": {"@type": "Person", "name": profile["name"], "url": SITE_URL},
              "description": w["description"], "url": f"{SITE_URL}/writing/{w['slug']}/",
              "isBasedOn": w["source"]}
        if og:
            ld["image"] = SITE_URL + og
        page(f"/writing/{w['slug']}/", w["title"], body, active="Writing", og_image=og, og_type="article",
             head_extra=jsonld(ld), description=w["description"] + ".")


def item_dl(i):
    title = link(i["url"], e(i["title"])) if i.get("url") else e(i["title"])
    extra = ""
    if i.get("writing") and i["writing"] in by_slug:
        extra = f'<div class="links-row"><a href="/writing/{i["writing"]}/">Article</a></div>'
    pic = i.get("image") or (pic_of(by_slug[i["writing"]]) if i.get("writing") in by_slug else None)
    text = f'{e(i["text"])}{extra}'
    if pic:
        target = i.get("url") or f'/writing/{i["writing"]}/'
        return (f'<dt>{title}</dt><dd><div class="with-img"><div>{text}</div>'
                f'<a class="thumb-link" href="{e(target)}" tabindex="-1" aria-hidden="true">{img_tag(pic, width=480)}</a></div></dd>')
    return f'<dt>{title}</dt><dd>{text}</dd>'


def build_projects():
    groups = "".join(
        f'<h2 class="section">{e(g["title"])}</h2><dl class="items">{"".join(item_dl(i) for i in g["items"])}</dl>'
        for g in projects["groups"])
    body = f"""
<div class="page-head"><h1>Projects</h1><p>{e(profile['pages']['projects'])}</p></div>
{groups}
"""
    page("/projects/", "Projects", body, active="Projects",
         description="Open-source software, production AI systems, safety-critical and clinical work, patents, and advisory by Yakov Shkolnikov.")


def build_lab():
    updates = "".join(writing_item({**by_slug[s], "description": lab["descriptions"].get(s, by_slug[s]["description"])})
                      for s in lab["series"] + lab["related"] if s in by_slug)
    setup = "".join(
        f'<h3 class="sub">{e(g["title"])}</h3>'
        f'<dl class="items">{"".join(item_dl(i) for i in g["items"])}</dl>'
        for g in lab["setup"])
    ph = lab["philosophy"]
    body = f"""
<div class="page-head"><h1>The Lab</h1><p>{e(lab['intro'])}</p></div>
<h2 class="section">Updates</h2>
<ul class="list">{updates}</ul>
<h2 class="section">Setup</h2>
<p class="prose"><strong>{e(ph['title'].replace('The Philosophy: ', ''))}.</strong> {e(ph['text'])}</p>
{setup}
"""
    page("/lab/", "The Lab", body, active="Lab", og_image=thumb(pic_of(by_slug[lab["series"][0]]), 1200)["src"],
         description="Soundness AI, Yakov Shkolnikov's independent AI research lab: progress updates and the hardware and tools behind the research.")


def build_about():
    bio = "".join(f"<p>{e(b)}</p>" for b in profile["bio"])
    principles = "".join(
        f'<h3>{e(p["title"])}</h3><p>{e(p["text"])}{" " + link(p["url"], "Read more") if p.get("url") else ""}</p>'
        for p in profile["principles"])
    m = profile["mentorship"]
    essay = next((w for w in writing if w["title"] == m["essay"]), None)
    essay_link = f' {link(essay["source"], "The Selfish Case for Mentorship")}' if essay else ""
    body = f"""
<div class="page-head"><h1>About</h1><p>{e(profile['headline'])}</p></div>
<div class="about-grid">
<div class="prose">{bio}<p class="meta">{e(profile['education'])}</p></div>
<figure>{img_tag(profile['portrait'], width=900, eager=True)}</figure>
</div>
<h2 class="section" id="principles">Principles</h2>
<p class="prose meta">{e(profile['pages']['principles'])}</p>
<div class="principles">{principles}</div>
<h2 class="section" id="mentorship">Mentorship</h2>
<div class="prose"><p>{e(profile['pages']['mentorship'])} {e(m['intro'])}</p><p>{e(m['invitation'])} {link(links_by['LinkedIn'], 'Reach out on LinkedIn')}.</p><p class="meta">Why I do it:{essay_link}</p></div>
"""
    page("/about/", "About", body, active="About", og_image=profile["portrait"]["src"],
         description=f"{profile['name']}: {profile['headline']}. Background, principles, and mentorship.")


def build_404():
    body = """<div class="page-head"><h1>Page not found</h1>
<p>The site was reorganized in September 2026. Try <a href="/writing/">Writing</a>, <a href="/research/">Research</a>, or the <a href="/">home page</a>.</p></div>"""
    page("/404.html", "Page not found", body, description="Page not found.")


def build_feed():
    def rfc822(d):
        from email.utils import format_datetime
        from datetime import datetime, timezone
        parts = [int(x) for x in d.split("-")] + [1]
        return format_datetime(datetime(parts[0], parts[1], parts[2], 12, tzinfo=timezone.utc))
    items = "".join(
        f"<item><title>{e(w['title'])}</title><link>{e(SITE_URL + href(w) if is_local(w) else w['source'])}</link>"
        f"<guid>{e(SITE_URL + href(w) if is_local(w) else w['source'])}</guid><pubDate>{rfc822(w['date'])}</pubDate>"
        f"<description>{e(w['description'])}.</description></item>"
        for w in writing[:30])
    (ROOT / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{e(profile["name"])}: Writing</title>'
        f"<link>{SITE_URL}/writing/</link><description>Essays on AI trust, agents, and AI at work.</description>"
        f"<language>en-us</language>{items}</channel></rss>\n")


def build_sitemap(paths):
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc></url>" for p in paths)
    (ROOT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")


def main():
    writing.sort(key=lambda w: w["date"], reverse=True)
    papers.sort(key=lambda p: p["date"], reverse=True)
    build_home()
    build_research()
    build_writing_index()
    build_articles()
    build_projects()
    build_lab()
    build_about()
    build_404()
    build_feed()
    paths = ["/", "/research/", "/writing/", "/projects/", "/lab/", "/about/"]
    paths += [f"/writing/{w['slug']}/" for w in writing if is_local(w)]
    paths += [f"/papers/{p['pdf']}" for p in papers]
    paths.append("/employment_july_2026.html")
    build_sitemap(paths)
    print(f"built {len(paths)} URLs: {sum(1 for w in writing if is_local(w))} articles, {len(papers)} papers")


if __name__ == "__main__":
    main()
