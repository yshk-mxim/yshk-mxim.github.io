#!/usr/bin/env python3
"""Import LinkedIn articles saved as Safari .webarchive files.

For each archive this writes:
  content/articles/<slug>.html   clean article body (semantic HTML only)
  writing/<slug>/*.webp          cover and inline images, resized
and adds or refreshes the matching entry in content/writing.json.
Hand-edited fields in writing.json (title, description, topic) are kept.

Usage: python3 tools/import_linkedin.py path/to/*.webarchive
Then:  python3 tools/build.py
"""
import io
import json
import plistlib
import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
MAX_WIDTH = 1600

KEEP_TAGS = {"p", "h2", "h3", "blockquote", "ul", "ol", "li", "strong", "em",
             "a", "br", "hr", "pre", "code", "figure", "img", "figcaption"}


def slug_from_url(url):
    path = urlparse(url).path.rstrip("/").split("/")[-1]
    path = re.sub(r"^copy-", "", path)
    # LinkedIn appends "-yakov-shkolnikov-xxxxx" (or just "-shkolnikov-xxxxx")
    path = re.sub(r"-(yakov-)?shkolnikov(-[a-z0-9]{4,6})?$", "", path)
    return path


def canonical(url):
    return url.split("?")[0].rstrip("/") + "/"


def clean_href(href):
    href = href.strip()
    if "](" in href:  # markdown debris in the original
        href = href.split("](", 1)[1].rstrip(")")
    u = urlparse(href)
    if u.netloc.endswith("linkedin.com") and u.path.startswith("/redir/"):
        href = unquote(parse_qs(u.query).get("url", [href])[0])
    if href.startswith("/"):
        href = "https://www.linkedin.com" + href
    return href


def save_image(data, dest, stem):
    im = Image.open(io.BytesIO(data))
    im = im.convert("RGBA") if im.mode in ("P", "LA") else im
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("RGB")
    if im.width > MAX_WIDTH:
        im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
    dest.mkdir(parents=True, exist_ok=True)
    name = f"{stem}.webp"
    im.save(dest / name, "WEBP", quality=82, method=6)
    return name, im.width, im.height


def simplify(node, resources, img_dir, counter):
    """Rewrite LinkedIn markup into plain semantic HTML, in place."""
    for c in node.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for junk in node.find_all(["section", "button", "svg", "label", "iframe"]):
        junk.decompose()

    for fig in node.find_all("figure"):
        img = fig.find("img")
        cap = fig.find("figcaption")
        caption = cap.get_text(" ", strip=True) if cap else ""
        data = resources.get(img["src"]) if img and img.get("src") else None
        if not data:
            fig.decompose()
            continue
        counter[0] += 1
        name, w, h = save_image(data, img_dir, f"fig-{counter[0]}")
        new = BeautifulSoup("", "html.parser").new_tag("figure")
        alt = img.get("alt", "")
        alt = caption if (not alt or alt == "Article content") else alt
        new.append(BeautifulSoup(
            f'<img src="{name}" alt="{escape(alt)}" width="{w}" height="{h}" loading="lazy">',
            "html.parser"))
        if caption:
            new.append(BeautifulSoup(f"<figcaption>{escape(caption)}</figcaption>", "html.parser"))
        # figures sit inside wrapper divs; hoist to block level
        top = fig
        while top.parent is not node and top.parent.name == "div":
            top = top.parent
        top.replace_with(new)

    for el in list(node.find_all(True)):
        if el.name in KEEP_TAGS:
            if el.name == "a":
                el.attrs = {"href": clean_href(el.get("href", ""))}
            elif el.name != "img":
                el.attrs = {}
        else:
            el.unwrap()

    # collapse the whitespace LinkedIn leaves around text nodes
    for s in node.find_all(string=True):
        if s.find_parent("pre"):
            continue
        t = re.sub(r"\s+", " ", str(s))
        s.replace_with(NavigableString(t))
    node.smooth()
    for el in node.find_all(["p", "h2", "h3", "li", "blockquote", "figcaption"]):
        if el.contents and isinstance(el.contents[0], NavigableString):
            el.contents[0].replace_with(el.contents[0].lstrip())
        if el.contents and isinstance(el.contents[-1], NavigableString):
            el.contents[-1].replace_with(el.contents[-1].rstrip())
    for p in node.find_all("p"):
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()


def to_html(node):
    html = "".join(str(c) for c in node.contents)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r">\s+<", ">\n<", html).strip()
    html = re.sub(r"\n(?=<(p|h2|h3|blockquote|ul|ol|figure|hr|pre)\b)", "\n\n", html)
    return html + "\n"


def import_archive(path, slugs):
    p = plistlib.load(open(path, "rb"))
    resources = {r["WebResourceURL"]: r["WebResourceData"] for r in p.get("WebSubresources", [])}
    soup = BeautifulSoup(p["WebMainResource"]["WebResourceData"].decode("utf-8"), "html.parser")
    art = soup.find("article")
    link = soup.find("link", rel="canonical")
    source = canonical(link["href"] if link else p["WebMainResource"]["WebResourceURL"])
    slug = slugs.get(source) or slug_from_url(source)
    title = " ".join(art.find("h1").get_text(" ", strip=True).split())
    t = art.find("time")
    date = datetime.strptime(t.get_text(strip=True), "%B %d, %Y").strftime("%Y-%m-%d")

    img_dir = ROOT / "writing" / slug
    for old in img_dir.glob("*.webp"):
        old.unlink()
    cover = None
    head_img = art.find("header").find("img")
    if head_img and resources.get(head_img.get("src")):
        name, w, h = save_image(resources[head_img["src"]], img_dir, "cover")
        cap = art.find("header").find("figcaption")
        cover = {"src": name, "width": w, "height": h,
                 "alt": (cap.get_text(" ", strip=True) if cap else head_img.get("alt", "")) or ""}

    body = art.find(class_="reader-content-blocks-container")
    simplify(body, resources, img_dir, [0])
    (CONTENT / "articles").mkdir(parents=True, exist_ok=True)
    (CONTENT / "articles" / f"{slug}.html").write_text(to_html(body))

    words = len(body.get_text(" ").split())
    return slug, {"slug": slug, "title": title, "date": date, "venue": "LinkedIn",
                  "source": source, "cover": cover, "words": words}


def main(paths):
    wpath = CONTENT / "writing.json"
    entries = json.loads(wpath.read_text()) if wpath.exists() else []
    by_slug = {e.get("slug"): e for e in entries if e.get("slug")}
    by_source = {canonical(e["source"]): e for e in entries if e.get("source")}
    slugs = {canonical(e["source"]): e["slug"] for e in entries if e.get("slug")}
    for path in paths:
        slug, meta = import_archive(path, slugs)
        existing = by_slug.get(slug) or by_source.get(meta["source"])
        if existing:
            for k in ("slug", "source", "cover", "words", "date"):
                existing[k] = meta[k]
            existing.setdefault("title", meta["title"])
            print(f"updated  {slug}")
        else:
            meta.update({"description": "", "topic": ""})
            entries.append(meta)
            by_slug[slug] = meta
            print(f"added    {slug}  (fill in description and topic)")
    entries.sort(key=lambda e: e["date"], reverse=True)
    wpath.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
