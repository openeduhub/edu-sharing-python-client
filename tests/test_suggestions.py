"""Metadaten vorschlagen, statt sie zu schreiben.

Ein Ablagefach mit Protokoll: eine Maschine schlaegt vor, ein Mensch
entscheidet. Genau die Trennung, die eine KI-Anwendung braucht.

Gemessen gegen Staging am 28.08.2026, und der wlo-mcp-sc hat am 01.08.2026
dasselbe gemessen:

* ``GET /suggestions/v1/-home-/{node}`` antwortet mit einer **Huelle**:
  ``{"nodeId": …, "suggestions": {}}``. Darin steht ein **Woerterbuch**, nach
  ``propertyId`` geschluesselt, mit je einer Liste.
* ``POST ?version=…`` nimmt eine **Liste** von
  ``{propertyId, value, description, confidence}`` und antwortet mit einer
  **Liste** der angelegten Vorschlaege -- je mit ``id``, ``status: "PENDING"``,
  ``created`` und ``createdBy``.
* ``PATCH ?status=ACCEPTED`` nimmt eine **Liste von IDs** und antwortet 200
  mit ``[]``.
* **Danach steht der Wert nicht am Knoten.** Gemessen blieb ``keywords`` leer.
  ``/suggestions/v1`` wendet nichts an -- es merkt sich, wer was
  vorgeschlagen und wer was entschieden hat. Das Anwenden bleibt Sache des
  Aufrufers, ueber den gewoehnlichen Schreibweg mit seiner Rueckleseprobe.
"""

import json

import httpx
import pytest

from edusharing import AsyncRepository
from edusharing.errors import SilentDropError
from edusharing.suggestions import Suggestion

REPO = "https://repo.test/edu-sharing"
NID = "k-1"


def _vorschlag(sid: str, prop: str, wert: str, *, status: str = "PENDING",
               why: str = "Weil", confidence: float | None = 0.9) -> dict:
    """Die gemessene Form eines Vorschlags."""
    return {"id": sid, "nodeId": NID, "version": "v1", "propertyId": prop,
            "value": wert, "type": None, "status": status, "description": why,
            "confidence": confidence,
            "created": "2026-08-28T10:15:17.962Z",
            "createdBy": {"authorityName": "alice", "authorityType": "USER"}}


class Instanz:
    def __init__(self, vorschlaege: list[dict] | None = None) -> None:
        self.vorschlaege = list(vorschlaege or [])
        self.anfragen: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.anfragen.append(request)
        if "/suggestions/v1" in request.url.path:
            if request.method == "GET":
                nach_property: dict[str, list[dict]] = {}
                for v in self.vorschlaege:
                    nach_property.setdefault(v["propertyId"], []).append(v)
                return httpx.Response(200, json={"nodeId": NID,
                                                 "suggestions": nach_property})
            if request.method == "POST":
                version = request.url.params.get("version") or "v1"
                neu = []
                for entwurf in json.loads(request.content):
                    v = _vorschlag(f"s-{len(self.vorschlaege) + len(neu) + 1}",
                                   entwurf["propertyId"], entwurf["value"],
                                   why=entwurf.get("description", ""),
                                   confidence=entwurf.get("confidence"))
                    v["version"] = version
                    neu.append(v)
                self.vorschlaege.extend(neu)
                return httpx.Response(200, json=neu)
            if request.method == "PATCH":
                # Wie die Instanz: die IDs stehen im Query. Ein Body wird
                # ignoriert -- gemessen, und der Grund fuer die Rueckleseprobe.
                status = request.url.params.get("status")
                for sid in request.url.params.get_list("id"):
                    for v in self.vorschlaege:
                        if v["id"] == sid:
                            v["status"] = status
                return httpx.Response(200, json=[])
        return httpx.Response(200, json={"node": {
            "ref": {"id": NID}, "type": "ccm:io", "name": "k.txt",
            "properties": {"cclom:title": ["Probe"]}}})

    def repo(self) -> AsyncRepository:
        return AsyncRepository(
            REPO, backoff_base=0.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))

    def letzte(self, methode: str) -> httpx.Request:
        for r in reversed(self.anfragen):
            if r.method == methode and "/suggestions/v1" in r.url.path:
                return r
        raise AssertionError(f"keine {methode}-Anfrage an /suggestions/v1")


# --- Lesen ----------------------------------------------------------------

async def test_ohne_vorschlaege_eine_leere_liste():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        assert await knoten.suggestions.list() == []


async def test_das_woerterbuch_wird_flach_gemacht():
    """Der Endpunkt schluesselt nach propertyId. Wer das Woerterbuch fuer eine
    Liste haelt, sieht bei einem Knoten mit mehreren Vorschlaegen keinen."""
    instanz = Instanz([_vorschlag("s-1", "cclom:general_keyword", "Zelle"),
                       _vorschlag("s-2", "cclom:general_keyword", "Biologie"),
                       _vorschlag("s-3", "ccm:taxonid", "Biologie")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        alle = await knoten.suggestions.list()
    assert len(alle) == 3
    assert {v.property for v in alle} == {"cclom:general_keyword", "ccm:taxonid"}


async def test_ein_vorschlag_wird_ausgelesen():
    instanz = Instanz([_vorschlag("s-1", "ccm:taxonid", "Biologie",
                                  why="Der Titel nennt Zellen", confidence=0.8)])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        (v,) = await knoten.suggestions.list()
    assert v == Suggestion(id="s-1", property="ccm:taxonid", value="Biologie",
                           status="PENDING", why="Der Titel nennt Zellen",
                           confidence=0.8, author="alice")


# --- Vorschlagen ----------------------------------------------------------

async def test_vorschlagen_schickt_eine_liste():
    """Der Endpunkt nimmt ein Array, auch fuer einen einzelnen Vorschlag."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil")
    koerper = json.loads(instanz.letzte("POST").content)
    assert isinstance(koerper, list)
    assert koerper[0] == {"propertyId": "ccm:taxonid", "value": "Biologie",
                          "description": "Weil"}


async def test_die_begruendung_ist_pflicht():
    """Ohne sie ist ein Vorschlag nicht pruefbar -- und der Endpunkt verlangt
    sie ohnehin."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(ValueError, match="reason"):
            await knoten.suggestions.propose("ccm:taxonid", "Biologie", "  ")


async def test_die_sicherheit_kommt_mit_wenn_sie_da_ist():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil",
                                         confidence=0.75)
    assert json.loads(instanz.letzte("POST").content)[0]["confidence"] == 0.75


async def test_der_angelegte_vorschlag_kommt_zurueck():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        neu = await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil")
    assert neu.id
    assert neu.status == "PENDING"
    assert neu.value == "Biologie"


async def test_eine_stapelmarke_wird_mitgeschickt():
    """Der Parameter ist am Endpunkt Pflicht und gruppiert einen Stapel."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil")
    assert instanz.letzte("POST").url.params["version"]


# --- Entscheiden ----------------------------------------------------------

async def test_annehmen_setzt_den_status():
    instanz = Instanz([_vorschlag("s-1", "ccm:taxonid", "Biologie")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.decide(["s-1"])
    patch = instanz.letzte("PATCH")
    assert patch.url.params["status"] == "ACCEPTED"
    assert patch.url.params.get_list("id") == ["s-1"], "IDs gehoeren in den Query"
    assert not patch.content, "ein Body wuerde ignoriert"


async def test_ablehnen_ebenso():
    instanz = Instanz([_vorschlag("s-1", "ccm:taxonid", "Biologie")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.decide(["s-1"], accept=False)
    assert instanz.letzte("PATCH").url.params["status"] == "DECLINED"


async def test_ohne_ids_wird_nicht_geschickt():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(ValueError):
            await knoten.suggestions.decide([])
    assert not [r for r in instanz.anfragen if "/suggestions/v1" in r.url.path]


async def test_annehmen_traegt_den_wert_nicht_ein():
    """Der Vorbehalt, den dieses Modul festhalten muss. Gemessen: nach
    ACCEPTED blieb keywords leer. Wer glaubt, der Wert stuende jetzt am Knoten,
    hat einen Datensatz, der aussieht wie gepflegt und keiner ist."""
    instanz = Instanz([_vorschlag("s-1", "cclom:general_keyword", "Zelle")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.decide(["s-1"])
        frisch = await repo.node(NID)
    assert frisch.keywords == [], "der Endpunkt wendet nichts an"
    staende = [v["status"] for v in instanz.vorschlaege]
    assert staende == ["ACCEPTED"], "nur der Stand wandert"


# --- Form -----------------------------------------------------------------

def test_suggestion_ist_unveraenderlich():
    v = Suggestion(id="s-1", property="p", value="w", status="PENDING",
                   why=None, confidence=None, author="alice")
    with pytest.raises(AttributeError):
        v.status = "ACCEPTED"  # type: ignore[misc]


def test_suggestion_repr_nennt_feld_wert_und_stand():
    v = Suggestion(id="s-1", property="ccm:taxonid", value="Biologie",
                   status="PENDING", why=None, confidence=None, author="alice")
    assert repr(v) == "Suggestion('ccm:taxonid'='Biologie', PENDING)"


async def test_ohne_feld_oder_wert_wird_nichts_geschickt():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(ValueError, match="property"):
            await knoten.suggestions.propose("", "Biologie", "Weil")
        with pytest.raises(ValueError, match="value"):
            await knoten.suggestions.propose("ccm:taxonid", "  ", "Weil")
    assert not [r for r in instanz.anfragen if "/suggestions/v1" in r.url.path]


async def test_eine_einzelne_id_als_zeichenkette_wird_verstanden():
    """Sonst entschiede decide("s-1") ueber je einen Vorschlag pro Buchstabe."""
    instanz = Instanz([_vorschlag("s-1", "ccm:taxonid", "Biologie")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.suggestions.decide("s-1")
    assert instanz.letzte("PATCH").url.params.get_list("id") == ["s-1"]


async def test_ein_nicht_angelegter_vorschlag_wird_gemeldet():
    """Antwortet die Instanz 200 mit leerer Liste, ist nichts entstanden -- ein
    stiller Verlust, und dafuer hat diese Bibliothek ihren eigenen Typ. Bis zum
    23.09.2026 kam er als ``ValueError`` und stand so in diesem Test:
    ``except SilentDropError`` ging an ihm vorbei, und ``as_result`` reichte
    ihn durch (Audit COR-23-2)."""
    class Taub(Instanz):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and "/suggestions/v1" in request.url.path:
                self.anfragen.append(request)
                return httpx.Response(200, json=[])
            return super().handler(request)

    instanz = Taub()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(SilentDropError, match="stored no proposal") as fehler:
            await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil")
    assert fehler.value.dropped == ["ccm:taxonid"]


async def test_reprs_nennen_den_knoten():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        assert NID in repr(knoten.suggestions)
        assert NID in repr(knoten.workflow)


async def test_eine_wirkungslose_entscheidung_wird_gemeldet():
    """Genau der Fall, den ein Live-Test beim Bauen gefangen hat: die IDs im
    Body statt im Query, 200 zurueck, und jeder Vorschlag bleibt PENDING."""
    from edusharing.errors import SilentDropError

    class Taub(Instanz):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.method == "PATCH" and "/suggestions/v1" in request.url.path:
                self.anfragen.append(request)
                return httpx.Response(200, json=[])
            return super().handler(request)

    instanz = Taub([_vorschlag("s-1", "ccm:taxonid", "Biologie")])
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(SilentDropError) as fehler:
            await knoten.suggestions.decide(["s-1"])
    assert "s-1" in fehler.value.dropped
