"""MantisSoapClient.create_issue / add_note 測試（mock 網路）。"""
from unittest.mock import patch, MagicMock

import pytest

from hcp_cms.services.mantis.soap import MantisSoapClient


@pytest.fixture
def client() -> MantisSoapClient:
    c = MantisSoapClient("http://mantis.test", "user", "pass")
    c._connected = True
    return c


def _mock_response(text: str, status: int = 200) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.text = text
    return m


def test_create_issue_success_returns_ticket_id(client: MantisSoapClient) -> None:
    response_xml = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<m:mc_issue_addResponse><return xsi:type="xsd:integer">12345</return></m:mc_issue_addResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        ticket_id = client.create_issue(
            project_id="1",
            summary="測試案件",
            description="本文",
        )
    assert ticket_id == "12345"


def test_create_issue_soap_fault_returns_none(client: MantisSoapClient) -> None:
    fault_xml = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<SOAP-ENV:Fault><faultstring>Access denied</faultstring></SOAP-ENV:Fault>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(fault_xml)
        result = client.create_issue(
            project_id="1",
            summary="x",
            description="y",
        )
    assert result is None
    assert "Access denied" in client.last_error


def test_create_issue_http_error_returns_none(client: MantisSoapClient) -> None:
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response("Server Error", status=500)
        result = client.create_issue(
            project_id="1",
            summary="x",
            description="y",
        )
    assert result is None
    assert "500" in client.last_error


def test_create_issue_includes_handler_when_provided(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            handler="YOGA",
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:handler>" in sent_body
    assert "<man:name>YOGA</man:name>" in sent_body


def test_create_issue_omits_handler_when_none(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">99</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="x",
            description="y",
            handler=None,
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "<man:handler>" not in sent_body


def test_create_issue_escapes_xml_in_summary(client: MantisSoapClient) -> None:
    response_xml = '<return xsi:type="xsd:integer">1</return>'
    with patch("hcp_cms.services.mantis.soap.requests.post") as mock_post:
        mock_post.return_value = _mock_response(response_xml)
        client.create_issue(
            project_id="1",
            summary="A & B <tag>",
            description="y",
        )
        sent_body = mock_post.call_args.kwargs.get("data", b"").decode("utf-8")
    assert "A &amp; B &lt;tag&gt;" in sent_body
