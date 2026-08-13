"""Tests for HTTP payload parsing"""
import asyncio
import json

import pytest

import plugins.formdata


class FakeRequest:
    def __init__(self, method="POST", query="", body="", content_type="", content_length=None):
        self.method = method
        self.query_string = query
        self.can_read_body = bool(body)
        self.content_length = content_length if content_length is not None else len(body)
        self.headers = {"content-type": content_type} if content_type else {}
        self._body = body

    async def text(self):
        return self._body


def parse(request, body_type="json"):
    return asyncio.run(plugins.formdata.parse_formdata(body_type, request))


def test_query_string_parameters_are_parsed():
    request = FakeRequest(method="GET", query="action=create&repository=httpd.git")
    assert parse(request) == {"action": "create", "repository": "httpd.git"}


def test_json_body_is_merged_with_the_query_string():
    request = FakeRequest(query="action=create", body=json.dumps({"repository": "httpd.git"}))
    assert parse(request) == {"action": "create", "repository": "httpd.git"}


def test_a_json_body_that_is_not_an_object_is_rejected():
    """Endpoints index into indata with string keys, so a bare list or scalar must never get through"""
    for body in ('["x"]', '"x"', "5"):
        with pytest.raises((ValueError, AssertionError)):
            parse(FakeRequest(body=body))


def test_a_malformed_json_body_is_rejected():
    with pytest.raises(ValueError):
        parse(FakeRequest(body="{not json"))


def test_urlencoded_form_bodies_are_parsed():
    request = FakeRequest(
        body="action=create&repository=httpd.git",
        content_type="application/x-www-form-urlencoded",
    )
    assert parse(request, body_type="form") == {"action": "create", "repository": "httpd.git"}


def test_multipart_form_bodies_are_parsed():
    body = (
        "--BOUND\r\n"
        'Content-Disposition: form-data; name="action"\r\n'
        "\r\n"
        "create\r\n"
        "--BOUND--\r\n"
    )
    request = FakeRequest(body=body, content_type="multipart/form-data; boundary=BOUND")
    assert parse(request, body_type="form") == {"action": "create"}


def test_oversized_payloads_are_rejected():
    request = FakeRequest(body="{}", content_length=plugins.formdata.BOXER_MAX_PAYLOAD + 1)
    with pytest.raises(ValueError):
        parse(request)
