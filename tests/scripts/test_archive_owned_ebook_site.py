import hashlib
import threading
import time

from scripts.archive_owned_ebook_site import (
    build_ebook_text,
    concurrent_map,
    discover_catalog_pages,
    fetch_catalog_books,
    parse_book_page,
    parse_catalog_books,
    parse_chapter,
    put_verified,
    select_pending_books,
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


def test_catalog_page_retries_when_success_response_contains_no_books():
    class FakeSite:
        def __init__(self):
            self.responses = ["<html>temporary challenge</html>", '<a href="/list/10.html">Book</a>']

        def get(self, path):
            return self.responses.pop(0)

    assert fetch_catalog_books(FakeSite(), "/book/17043_2.html", retry_delay=0) == ["/list/10.html"]


def test_catalog_page_fails_closed_after_repeated_empty_responses():
    class EmptySite:
        def get(self, path):
            return "<html>temporary challenge</html>"

    import pytest

    with pytest.raises(RuntimeError, match="catalog page contains no books"):
        fetch_catalog_books(EmptySite(), "/book/17043_2.html", retry_delay=0)


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


def test_existing_books_are_not_rescheduled_when_skip_existing_is_enabled():
    paths = ["/list/1.html", "/list/2.html", "/list/3.html"]

    assert select_pending_books(paths, {"1", "3"}, skip_existing=True) == ["/list/2.html"]
    assert select_pending_books(paths, {"1", "3"}, skip_existing=False) == paths


def test_concurrent_map_runs_up_to_eight_workers_without_losing_results():
    lock = threading.Lock()
    active = 0
    peak = 0

    def worker(value):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 2

    results = list(concurrent_map(worker, range(16), concurrency=8))

    assert sorted(results) == [value * 2 for value in range(16)]
    assert peak == 8
