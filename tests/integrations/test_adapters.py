"""Contract and unit tests for search engine isolated adapters."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.integrations.adapters.bing import BingWebmasterAdapter
from apps.integrations.adapters.google import GoogleSearchConsoleAdapter
from apps.integrations.adapters.indexnow import IndexNowAdapter


def test_google_submit_sitemap_success() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    session.put.return_value = mock_resp

    adapter = GoogleSearchConsoleAdapter(
        site_url="https://example.com",
        access_token="fake-token",  # nosec B106
        session=session,
    )
    res = adapter.submit_sitemap("https://example.com/sitemap.xml")

    assert res["status"] == "SUCCESS"
    assert res["provider"] == "GOOGLE"
    assert session.put.called
    called_url = session.put.call_args[0][0]
    assert "https%3A%2F%2Fexample.com" in called_url


def test_google_submit_sitemap_failure() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.text = "Permission denied"
    session.put.return_value = mock_resp

    adapter = GoogleSearchConsoleAdapter(
        site_url="https://example.com",
        access_token="fake-token",  # nosec B106
        session=session,
    )
    res = adapter.submit_sitemap("https://example.com/sitemap.xml")

    assert res["status"] == "ERROR"
    assert res["code"] == 403
    assert res["error"] == "Permission denied"


def test_google_inspect_url_success() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "inspectionResult": {
            "indexStatusResult": {
                "verdict": "PASS",
                "coverageState": "Submitted and indexed",
            }
        }
    }
    session.post.return_value = mock_resp

    adapter = GoogleSearchConsoleAdapter(
        site_url="https://example.com",
        access_token="fake-token",  # nosec B106
        session=session,
    )
    res = adapter.inspect_url("https://example.com/blog/my-post")

    assert res["status"] == "SUCCESS"
    assert res["verdict"] == "PASS"
    assert res["coverage_state"] == "Submitted and indexed"


def test_google_inspect_url_error() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "Site not found"
    session.post.return_value = mock_resp

    adapter = GoogleSearchConsoleAdapter(
        site_url="https://example.com",
        access_token="fake-token",  # nosec B106
        session=session,
    )
    res = adapter.inspect_url("https://example.com/unknown")

    assert res["status"] == "ERROR"
    assert res["code"] == 404


def test_google_submit_urls_disallowed() -> None:
    adapter = GoogleSearchConsoleAdapter(
        site_url="https://example.com",
        access_token="fake-token",  # nosec B106
    )
    with pytest.raises(ValueError, match="Google Indexing API does not support"):
        adapter.submit_urls(["https://example.com/test"])


def test_bing_submit_sitemap_success() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    session.get.return_value = mock_resp

    adapter = BingWebmasterAdapter(
        site_url="https://example.com",
        api_key="bing-key-123",  # nosec B106
        session=session,
    )
    res = adapter.submit_sitemap("https://example.com/sitemap.xml")

    assert res["status"] == "SUCCESS"
    assert res["provider"] == "BING"
    assert session.get.called


def test_bing_submit_sitemap_failure() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    session.get.return_value = mock_resp

    adapter = BingWebmasterAdapter(
        site_url="https://example.com",
        api_key="bing-key-123",  # nosec B106
        session=session,
    )
    res = adapter.submit_sitemap("https://example.com/sitemap.xml")

    assert res["status"] == "ERROR"
    assert res["code"] == 500


def test_bing_submit_urls_batch() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    session.post.return_value = mock_resp

    adapter = BingWebmasterAdapter(
        site_url="https://example.com",
        api_key="bing-key-123",  # nosec B106
        session=session,
    )
    urls = ["https://example.com/p1", "https://example.com/p2"]
    res = adapter.submit_urls(urls)

    assert res["status"] == "SUCCESS"
    assert res["submitted_count"] == 2
    assert session.post.called


def test_bing_submit_urls_empty() -> None:
    adapter = BingWebmasterAdapter(site_url="https://example.com", api_key="k")  # nosec B106
    res = adapter.submit_urls([])
    assert res["status"] == "SUCCESS"
    assert res["submitted_count"] == 0


def test_indexnow_submit_urls_success() -> None:
    session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    session.post.return_value = mock_resp

    adapter = IndexNowAdapter(
        host="example.com",
        key="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        session=session,
    )
    urls = ["https://example.com/page-1", "https://example.com/page-2"]
    res = adapter.submit_urls(urls)

    assert res["status"] == "SUCCESS"
    assert res["code"] == 200
    assert res["submitted_count"] == 2
    assert session.post.called


def test_indexnow_submit_urls_exceeds_max_bound() -> None:
    adapter = IndexNowAdapter(
        host="example.com",
        key="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    )
    large_list = [f"https://example.com/{i}" for i in range(10001)]
    with pytest.raises(ValueError, match="IndexNow batches cannot exceed 10000"):
        adapter.submit_urls(large_list)


def test_indexnow_submit_sitemap_unsupported() -> None:
    adapter = IndexNowAdapter(
        host="example.com",
        key="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
    )
    with pytest.raises(NotImplementedError, match="IndexNow does not support XML sitemap"):
        adapter.submit_sitemap("https://example.com/sitemap.xml")
