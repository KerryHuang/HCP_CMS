"""測試 MantisSoapClient 新欄位解析。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hcp_cms.services.mantis.base import MantisIssue, MantisNote
from hcp_cms.services.mantis.soap import MantisSoapClient


def test_mantis_issue_has_new_fields():
    issue = MantisIssue(id="1", summary="test")
    assert issue.severity == ""
    assert issue.reporter == ""
    assert issue.date_submitted == ""
    assert issue.target_version == ""
    assert issue.fixed_in_version == ""
    assert issue.description == ""
    assert issue.notes_list == []
    assert issue.notes_count == 0


def test_mantis_note_fields():
    note = MantisNote()
    assert note.note_id == ""
    assert note.reporter == ""
    assert note.text == ""
    assert note.date_submitted == ""


_SAMPLE_SOAP = """<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                   xmlns:ns1="http://futureware.biz/mantisconnect">
  <SOAP-ENV:Body>
    <ns1:mc_issue_getResponse>
      <return xsi:type="ns1:IssueData">
        <id xsi:type="xsd:integer">17186</id>
        <summary xsi:type="xsd:string">薪資計算錯誤</summary>
        <severity xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">50</id>
          <name xsi:type="xsd:string">major</name>
        </severity>
        <priority xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">40</id>
          <name xsi:type="xsd:string">high</name>
        </priority>
        <status xsi:type="ns1:ObjectRef">
          <id xsi:type="xsd:integer">80</id>
          <name xsi:type="xsd:string">resolved</name>
        </status>
        <reporter xsi:type="ns1:AccountData">
          <id xsi:type="xsd:integer">5</id>
          <name xsi:type="xsd:string">林美麗</name>
        </reporter>
        <handler xsi:type="ns1:AccountData">
          <id xsi:type="xsd:integer">3</id>
          <name xsi:type="xsd:string">王小明</name>
        </handler>
        <date_submitted xsi:type="xsd:dateTime">2026-01-15T10:00:00+08:00</date_submitted>
        <target_version xsi:type="xsd:string">v2.5.1</target_version>
        <fixed_in_version xsi:type="xsd:string">v2.5.2</fixed_in_version>
        <description xsi:type="xsd:string">月底批次薪資計算時發生加班費錯誤。</description>
        <notes>
          <item xsi:type="ns1:IssueNoteData">
            <id xsi:type="xsd:integer">101</id>
            <reporter xsi:type="ns1:AccountData">
              <name xsi:type="xsd:string">王小明</name>
            </reporter>
            <text xsi:type="xsd:string">已確認問題根因。</text>
            <date_submitted xsi:type="xsd:dateTime">2026-01-16T09:00:00+08:00</date_submitted>
          </item>
          <item xsi:type="ns1:IssueNoteData">
            <id xsi:type="xsd:integer">102</id>
            <reporter xsi:type="ns1:AccountData">
              <name xsi:type="xsd:string">王小明</name>
            </reporter>
            <text xsi:type="xsd:string">修復完畢，已合併至 v2.5.2。</text>
            <date_submitted xsi:type="xsd:dateTime">2026-01-20T14:00:00+08:00</date_submitted>
          </item>
        </notes>
      </return>
    </ns1:mc_issue_getResponse>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


def test_get_issue_parses_severity_and_reporter():
    client = MantisSoapClient("https://example.com/mantis", "user", "pass")
    client._connected = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SAMPLE_SOAP
    with patch("requests.post", return_value=mock_resp):
        issue = client.get_issue("17186")
    assert issue is not None
    assert issue.summary == "薪資計算錯誤"
    assert issue.severity == "major"
    assert issue.reporter == "林美麗"
    assert issue.handler == "王小明"
    assert issue.status == "resolved"
    assert issue.target_version == "v2.5.1"
    assert issue.fixed_in_version == "v2.5.2"
    assert "加班費" in issue.description


def test_get_issue_parses_notes():
    client = MantisSoapClient("https://example.com/mantis", "user", "pass")
    client._connected = True
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = _SAMPLE_SOAP
    with patch("requests.post", return_value=mock_resp):
        issue = client.get_issue("17186")
    assert issue is not None
    assert issue.notes_count == 2
    assert len(issue.notes_list) == 2
    # 最新在前（降序）
    assert issue.notes_list[0].text == "修復完畢，已合併至 v2.5.2。"
    assert issue.notes_list[1].text == "已確認問題根因。"


def test_parse_notes_max_5():
    """超過 5 條時 notes_list 只取最後 5 條，notes_count 保留總數。"""
    items = "".join(
        f"""<item xsi:type="ns1:IssueNoteData">
          <id xsi:type="xsd:integer">{i}</id>
          <reporter xsi:type="ns1:AccountData"><name xsi:type="xsd:string">u{i}</name></reporter>
          <text xsi:type="xsd:string">note {i}</text>
          <date_submitted xsi:type="xsd:dateTime">2026-01-{i:02d}T00:00:00+08:00</date_submitted>
        </item>"""
        for i in range(1, 8)
    )
    xml = _SAMPLE_SOAP.replace("<notes>", f"<notes>{items}")
    notes, count = MantisSoapClient._parse_notes(xml, max_count=5)
    assert count == 9
    assert len(notes) == 5
