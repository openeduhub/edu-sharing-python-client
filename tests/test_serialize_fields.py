"""Was ein Treffer zeigt: Vorschau, Download, Lizenz, Groesse -- und jede
gewuenschte Eigenschaft.

Der MCP gibt je Treffer previewUrl, downloadUrl, license, mimeType, fileSize.
Die Bibliothek trug all das nur in ``raw`` -- und ``collection_contents``
verschwieg gemessen die Inhaltsart, obwohl das Listing sie liefert, weil
``fields`` nur die konfigurierten Kurznamen kennt. ``properties=`` nennt die
Eigenschaften, die zusaetzlich unter ``fields`` erscheinen sollen, mit ihrem
vollen Namen.
"""

import pytest

from edusharing.flows.serialize import hit_as_dict
from edusharing.results import SearchHit

REPO = "https://repo.test/edu-sharing"
ALIASES = {"subject": "ccm:taxonid"}


def _hit(**extra) -> SearchHit:
    node = {
        "ref": {"id": "n-1"}, "title": "T", "type": "ccm:io",
        "downloadUrl": f"{REPO}/rest/node/v1/nodes/-home-/n-1/content",
        "preview": {"url": f"{REPO}/preview?nodeId=n-1", "isIcon": False},
        "mimetype": "application/pdf",
        "properties": {
            "cclom:title": ["T"], "cclom:size": ["12345"],
            "ccm:commonlicense_key": ["CC_BY"],
            "ccm:oeh_extendedType": ["http://w3id.org/openeduhub/vocabs/contentTypes/ai_skill"],
            "ccm:taxonid": ["http://x/080"], "ccm:taxonid_DISPLAYNAME": ["Biologie"],
        },
    }
    node.update(extra)
    return SearchHit.from_node(node, REPO)


def test_ein_treffer_kennt_vorschau_download_lizenz_und_groesse():
    hit = _hit()
    assert hit.preview_url == f"{REPO}/preview?nodeId=n-1"
    assert hit.download_url == f"{REPO}/rest/node/v1/nodes/-home-/n-1/content"
    assert hit.license == "CC_BY"
    assert hit.size == 12345


@pytest.mark.parametrize("gespeichert", ["²", "١٢", "12.5", "-3", " 7"])
def test_eine_groesse_zaehlt_nur_in_ascii_ziffern(gespeichert):
    """Audit COR-23-5 (23.09.2026): ``"²".isdigit()`` ist wahr, ``int("²")``
    wirft ``ValueError``. ASCII-Ziffern, wie bei Content-Length und
    Retry-After -- das Repositorium schreibt ``cclom:size`` selbst, anders
    geschrieben ist es nicht von ihm."""
    hit = SearchHit.from_node(
        {"ref": {"id": "n-1"}, "properties": {"cclom:size": [gespeichert]}}, REPO)
    assert hit.size is None


def test_ein_typsymbol_ist_keine_vorschau():
    """Gemessen am 28.08.2026: preview.url ist immer gesetzt, auch fuer das
    Symbol des Dateityps. isIcon unterscheidet -- wie bei Node.preview_url."""
    hit = _hit(preview={"url": "https://x/icon.svg", "isIcon": True})
    assert hit.preview_url is None


def test_hit_as_dict_traegt_die_vier_felder():
    got = hit_as_dict(_hit(), ALIASES)
    assert got["preview_url"] == f"{REPO}/preview?nodeId=n-1"
    assert got["download_url"] == f"{REPO}/rest/node/v1/nodes/-home-/n-1/content"
    assert got["license"] == "CC_BY"
    assert got["size"] == 12345


def test_gewuenschte_eigenschaften_erscheinen_unter_fields():
    got = hit_as_dict(_hit(), ALIASES, properties=["ccm:oeh_extendedType", "ccm:nicht_da"])
    assert got["fields"]["subject"] == ["Biologie"]
    assert got["fields"]["ccm:oeh_extendedType"] == [
        "http://w3id.org/openeduhub/vocabs/contentTypes/ai_skill"]
    assert "ccm:nicht_da" not in got["fields"], "eine fehlende Eigenschaft wird nicht erfunden"


def test_ohne_wunsch_bleibt_fields_wie_bisher():
    got = hit_as_dict(_hit(), ALIASES)
    assert set(got["fields"]) == {"subject"}
