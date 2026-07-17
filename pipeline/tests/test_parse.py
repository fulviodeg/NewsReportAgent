from email.message import EmailMessage

from src.ingest.base import RawMessage
from src.parse import parse_email

DIGEST_HTML = """
<html><body>
  <h1>Daily Tech Digest</h1>
  <div class="item">
    <a href="https://news.example.com/apple-m5">Apple unveils the M5 chip</a>
    <p>Apple announced its next-generation M5 processor today, promising big gains.</p>
  </div>
  <div class="item">
    <a href="https://news.example.com/openai-round">OpenAI raises a new funding round</a>
    <p>OpenAI closed a large round to expand its compute footprint.</p>
  </div>
  <p><a href="https://example.com/unsubscribe">Unsubscribe</a> from this newsletter</p>
  <p><a href="https://twitter.com/acme">Follow us on Twitter</a></p>
</body></html>
"""


def _raw_from_html(html: str) -> RawMessage:
    msg = EmailMessage()
    msg["From"] = "News <news@example.com>"
    msg["Subject"] = "Digest"
    msg.set_content("plain fallback")
    msg.add_alternative(html, subtype="html")
    return RawMessage("news@example.com", "News", "Digest", "", "<id@x>", msg)


def test_parse_splits_digest_and_skips_boilerplate():
    items = parse_email(_raw_from_html(DIGEST_HTML))
    links = [i.link for i in items]
    assert "https://news.example.com/apple-m5" in links
    assert "https://news.example.com/openai-round" in links
    # unsubscribe + social links are filtered out
    assert not any("unsubscribe" in l for l in links)
    assert not any("twitter" in l for l in links)
    apple = next(i for i in items if i.link.endswith("apple-m5"))
    assert apple.title == "Apple unveils the M5 chip"
    assert "M5 processor" in apple.text
    assert apple.content_hash


def test_parse_hint_selects_containers():
    items = parse_email(_raw_from_html(DIGEST_HTML), parse_hint="div.item")
    assert len(items) == 2
    assert all(i.link.startswith("https://news.example.com/") for i in items)


def test_parse_content_hash_is_stable():
    a = parse_email(_raw_from_html(DIGEST_HTML))
    b = parse_email(_raw_from_html(DIGEST_HTML))
    assert [i.content_hash for i in a] == [i.content_hash for i in b]


def test_parse_plain_text_fallback():
    msg = EmailMessage()
    msg["From"] = "news@example.com"
    msg.set_content(
        "Big story about AI here. Read more at https://example.com/story-1\n\n"
        "Another one: https://example.com/story-2 with details."
    )
    raw = RawMessage("news@example.com", "", "s", "", "<id>", msg)
    items = parse_email(raw)
    links = {i.link for i in items}
    assert "https://example.com/story-1" in links
    assert "https://example.com/story-2" in links
