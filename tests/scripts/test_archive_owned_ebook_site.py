import hashlib

from scripts.archive_owned_ebook_site import (
    build_ebook_text,
    discover_catalog_pages,
    parse_book_page,
    parse_catalog_books,
    parse_chapter,
    put_verified,
)


def test_discovers_full_catalog_without_following_unrelated_links():
    html = """
    <a href="/list/10.html">Book A</a>
    <a href="/book/17043_2.html">2</a>
    <a class="endPage" href="/book/17043_569.html">last</a>
    <a href="/writer/3.html">author</a>
    """

    assert discover_catalog_pages(html) == [
        "/book/index.html",
        *[f"/book/17043_{page}.html" for page in range(2, 570)],
    ]
    assert parse_catalog_books(html) == ["/list/10.html"]


def test_parses_only_chapters_from_the_book_chapter_lists():
    html = """
    <h1 class="page-title">Book A</h1>
    <a class="author" href="/writer/3.html">Author A</a>
    <div class="mod book-intro"><div class="bd"> Intro text </div></div>
    <div class="mod block update chapter-list"><div class="bd"><ul class="list">
      <li><a href="/view/101.html">Chapter 1</a></li>
      <li><a href="/view/102.html">Chapter 2</a></li>
    </ul></div></div>
    <div class="tuijian"><a href="/view/999.html">Unrelated</a></div>
    """

    book = parse_book_page("/list/10.html", html)

    assert book.book_id == "10"
    assert book.title == "Book A"
    assert book.author == "Author A"
    assert book.intro == "Intro text"
    assert book.chapter_paths == ("/view/101.html", "/view/102.html")


def test_extracts_clean_chapter_text_and_builds_stable_txt():
    html = """
    <h1 class="page-title">Chapter 1</h1>
    <div id="nr1">First line<br><br>Second &amp; final line</div>
    <div class="tuijian">Advertisement</div>
    """

    chapter = parse_chapter("/view/101.html", html)
    payload = build_ebook_text("Book A", "Author A", "Intro", [chapter])

    assert chapter.title == "Chapter 1"
    assert chapter.text == "First line\n\nSecond & final line"
    assert "Advertisement" not in payload
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_nas_upload_is_read_back_before_acceptance():
    class FakeS3:
        def __init__(self):
            self.objects = {}

        def put_object(self, *, Bucket, Key, Body, **kwargs):
            self.objects[(Bucket, Key)] = Body

        def get_object(self, *, Bucket, Key):
            payload = self.objects[(Bucket, Key)]
            return {"Body": type("Body", (), {"iter_chunks": lambda self: [payload]})()}

    payload = b"owned ebook"
    put_verified(FakeS3(), "archive", "ebooks/1.txt", payload, content_type="text/plain")
