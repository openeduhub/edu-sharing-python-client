"""Vorschaubild, Blaettern durch Kinder, Sammlung aendern.

Drei kleine Luecken an vorhandenen Stellen. Gemessen gegen Staging am
28.08.2026:

**Vorschaubild.** Das Multipart-Feld heisst ``image``. Mit ``file`` antwortet
der Endpunkt ``500 NullPointerException: inputStream`` -- ein Name, den man
nicht raten kann und der nichts erklaert.

``preview.url`` steht **immer** in der Antwort, auch ohne Vorschaubild und
sogar nach dem Loeschen (mit neuem ``dontcache``). Dieselbe Falle wie bei
``downloadUrl``. Was unterscheidet, ist ``isIcon``:

====================  ==========  ==============  ====================
Zustand               ``isIcon``  ``isGenerated``  ``type``
====================  ==========  ==============  ====================
ohne Vorschaubild     ``true``    ``true``         ``TYPE_DEFAULT``
mit eigenem Bild      ``false``   ``false``        ``TYPE_USERDEFINED``
nach dem Loeschen     ``true``    ``true``         ``TYPE_DEFAULT``
====================  ==========  ==============  ====================

**Blaettern.** ``sortProperties`` und ``sortAscending`` wirken, ``skipCount``
ebenso, ``pagination`` traegt ``{total, from, count}``. Ohne
``propertyFilter=-all-`` kommen die Kinder ohne Eigenschaften.

**Sammlung aendern.** ``ref.id`` im Body ist Pflicht -- ohne endet der Aufruf in
``500 NullPointerException`` (``NodeRef.getId()``), die ID im Pfad genuegt
nicht. Die Beschreibung gehoert **in das ``collection``-Objekt**: als
``properties["cm:description"]`` wird sie still verworfen. Und ein neuer Titel
aendert auch ``cm:name`` -- Umbenennen benennt den Knoten mit um.
"""

import json

import httpx
import pytest

from edusharing import AsyncRepository
from edusharing.nodes import ChildPage

REPO = "https://repo.test/edu-sharing"
NID = "k-1"
PNG = b"\x89PNG\r\n\x1a\n"


def _knoten(nid: str, name: str, *, typ: str = "ccm:io",
            preview: dict | None = None) -> dict:
    return {"ref": {"id": nid}, "name": name, "type": typ,
            "preview": preview if preview is not None
            else {"url": f"https://repo.test/preview?nodeId={nid}",
                  "isIcon": True, "isGenerated": True, "type": "TYPE_DEFAULT"},
            "properties": {"cm:name": [name], "cclom:title": [name]}}


class Instanz:
    def __init__(self, kinder: list[dict] | None = None) -> None:
        self.kinder = kinder if kinder is not None else [
            _knoten(f"c-{i}", f"s{i}.txt") for i in range(5)]
        self.eigenes_bild = False
        self.sammlung = {"titel": "Alt", "beschreibung": "Alt", "name": "Alt"}
        self.anfragen: list[httpx.Request] = []

    def _preview(self) -> dict:
        return {"url": "https://repo.test/preview?nodeId=k-1",
                "isIcon": not self.eigenes_bild,
                "isGenerated": not self.eigenes_bild,
                "type": "TYPE_USERDEFINED" if self.eigenes_bild
                else "TYPE_DEFAULT"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.anfragen.append(request)
        pfad, methode = request.url.path, request.method

        if pfad.endswith("/preview"):
            self.eigenes_bild = methode == "POST"
            return httpx.Response(200, json={"node": _knoten(
                NID, "k.txt", preview=self._preview())})

        if pfad.endswith("/children") and methode == "GET":
            ab = int(request.url.params.get("skipCount") or 0)
            wieviel = int(request.url.params.get("maxItems") or 10)
            auf = (request.url.params.get("sortAscending") or "true") == "true"
            sortiert = sorted(self.kinder, key=lambda n: n["name"], reverse=not auf)
            ausschnitt = sortiert[ab:ab + wieviel]
            return httpx.Response(200, json={
                "nodes": ausschnitt,
                "pagination": {"total": len(self.kinder), "from": ab,
                               "count": len(ausschnitt)}})

        if "/collection/v1/collections" in pfad and methode == "PUT":
            koerper = json.loads(request.content)
            self.sammlung["titel"] = koerper.get("title", self.sammlung["titel"])
            self.sammlung["name"] = self.sammlung["titel"]
            beschreibung = (koerper.get("collection") or {}).get("description")
            if beschreibung is not None:
                self.sammlung["beschreibung"] = beschreibung
            return httpx.Response(200, content=b"")

        if "/collection/v1/collections" in pfad:
            return httpx.Response(200, json={"collection": {
                "ref": {"id": "s-1"}, "type": "ccm:map",
                "name": self.sammlung["name"], "title": self.sammlung["titel"],
                "properties": {"cm:title": [self.sammlung["titel"]],
                               "cm:name": [self.sammlung["name"]],
                               "cm:description": [self.sammlung["beschreibung"]]}}})

        nid = "s-1" if "s-1" in pfad else NID
        if nid == "s-1":
            return httpx.Response(200, json={"node": {
                "ref": {"id": "s-1"}, "type": "ccm:map",
                "name": self.sammlung["name"], "title": self.sammlung["titel"],
                "properties": {"cm:title": [self.sammlung["titel"]],
                               "cm:name": [self.sammlung["name"]],
                               "cm:description": [self.sammlung["beschreibung"]]}}})
        return httpx.Response(200, json={"node": _knoten(
            NID, "k.txt", preview=self._preview())})

    def repo(self) -> AsyncRepository:
        return AsyncRepository(
            REPO, backoff_base=0.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))

    def letzte(self, methode: str, teil: str = "") -> httpx.Request:
        for r in reversed(self.anfragen):
            if r.method == methode and teil in r.url.path:
                return r
        raise AssertionError(f"keine {methode}-Anfrage mit {teil!r}")


# --- Vorschaubild ---------------------------------------------------------

async def test_ohne_eigenes_bild_gibt_es_keine_adresse():
    """preview.url steht immer da, auch ohne Bild -- wer sie durchreicht,
    zeigt ein Typ-Symbol und haelt es fuer eine Vorschau."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
    assert knoten.preview_url is None


async def test_mit_eigenem_bild_kommt_die_adresse():
    instanz = Instanz()
    instanz.eigenes_bild = True
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
    assert knoten.preview_url == "https://repo.test/preview?nodeId=k-1"


async def test_das_feld_heisst_image():
    """Mit ``file`` antwortet der Endpunkt 500 NullPointerException:
    inputStream -- ein Name, den man nicht raten kann."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.content.set_preview(PNG)
    post = instanz.letzte("POST", "/preview")
    assert b'name="image"' in post.content
    assert post.url.params["mimetype"] == "image/png"


async def test_setzen_gibt_den_frischen_knoten():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        danach = await knoten.content.set_preview(PNG)
    assert danach.preview_url is not None


async def test_loeschen_nimmt_die_adresse_wieder_weg():
    instanz = Instanz()
    instanz.eigenes_bild = True
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        danach = await knoten.content.delete_preview()
    assert danach.preview_url is None


async def test_ein_leeres_bild_wird_abgelehnt():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        with pytest.raises(ValueError, match="empty"):
            await knoten.content.set_preview(b"")
    assert not [r for r in instanz.anfragen if r.url.path.endswith("/preview")]


# --- Blaettern ------------------------------------------------------------

async def test_kinder_kommen_als_seite():
    instanz = Instanz()
    async with instanz.repo() as repo:
        seite = await repo.nodes.children(NID, limit=2)
    assert isinstance(seite, ChildPage)
    assert [n.name for n in seite.nodes] == ["s0.txt", "s1.txt"]
    assert seite.total == 5
    assert seite.offset == 0


async def test_blaettern_ueberspringt():
    instanz = Instanz()
    async with instanz.repo() as repo:
        seite = await repo.nodes.children(NID, limit=2, offset=2)
    assert [n.name for n in seite.nodes] == ["s2.txt", "s3.txt"]
    assert seite.offset == 2


async def test_absteigend_sortieren():
    instanz = Instanz()
    async with instanz.repo() as repo:
        seite = await repo.nodes.children(NID, limit=2, ascending=False)
    assert [n.name for n in seite.nodes] == ["s4.txt", "s3.txt"]


async def test_ohne_sortierung_waere_blaettern_unzuverlaessig():
    """Deshalb gibt es eine Vorgabe: ueber eine ungeordnete Liste zu blaettern
    kann Eintraege doppelt bringen und andere auslassen."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.nodes.children(NID)
    assert instanz.letzte("GET", "/children").url.params["sortProperties"] == "cm:name"


async def test_die_eigenschaften_kommen_mit():
    """Ohne propertyFilter=-all- kaemen die Kinder ohne Titel -- gemessen und
    schon in discover.py festgehalten."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        seite = await repo.nodes.children(NID)
    assert instanz.letzte("GET", "/children").url.params["propertyFilter"] == "-all-"
    assert seite.nodes[0].title


async def test_nur_dateien():
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.nodes.children(NID, only="files")
    assert instanz.letzte("GET", "/children").url.params["filter"] == "files"


async def test_ohne_einschraenkung_kein_filter():
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.nodes.children(NID)
    assert "filter" not in instanz.letzte("GET", "/children").url.params


async def test_eine_leere_seite_ist_kein_fehler():
    instanz = Instanz(kinder=[])
    async with instanz.repo() as repo:
        seite = await repo.nodes.children(NID)
    assert seite.nodes == ()
    assert seite.total == 0


# --- Sammlung aendern -----------------------------------------------------

async def test_umbenennen_schickt_die_id_im_body():
    """Ohne ref.id endet der Aufruf in 500 -- die ID im Pfad genuegt nicht,
    das DTO wird gelesen."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.collections.update("s-1", title="Neu")
    koerper = json.loads(instanz.letzte("PUT", "/collection").content)
    assert koerper["ref"]["id"] == "s-1"
    assert koerper["title"] == "Neu"


async def test_die_beschreibung_geht_ins_collection_objekt():
    """Als properties['cm:description'] wird sie still verworfen -- gemessen."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.collections.update("s-1", title="Neu", description="Text")
    koerper = json.loads(instanz.letzte("PUT", "/collection").content)
    assert koerper["collection"]["description"] == "Text"
    assert "cm:description" not in koerper.get("properties", {})


async def test_umbenennen_liest_zurueck():
    instanz = Instanz()
    async with instanz.repo() as repo:
        danach = await repo.collections.update("s-1", title="Neu",
                                               description="Text")
    assert danach.title == "Neu"
    assert danach.get("cm:description") == "Text"


async def test_umbenennen_aendert_auch_den_namen():
    """Gemessen: title, cm:title und cm:name stehen danach alle auf dem neuen
    Wert. Wer den technischen Namen behalten will, muss das wissen."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        danach = await repo.collections.update("s-1", title="Neu")
    assert danach.name == "Neu"


async def test_nur_die_beschreibung_aendern_behaelt_den_titel():
    """Der Endpunkt verlangt title als Pflichtfeld -- ohne ihn endet er in
    'cmNameReadableName is null'. Also muss der bestehende mitgeschickt
    werden, was einen Lesevorgang kostet."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        danach = await repo.collections.update("s-1", description="Nur das")
    koerper = json.loads(instanz.letzte("PUT", "/collection").content)
    assert koerper["title"] == "Alt", "der bestehende Titel wird mitgeschickt"
    assert danach.title == "Alt"


async def test_ohne_aenderung_wird_nicht_geschrieben():
    instanz = Instanz()
    async with instanz.repo() as repo:
        with pytest.raises(ValueError, match="title or description"):
            await repo.collections.update("s-1")
    assert not [r for r in instanz.anfragen if r.method == "PUT"]


# --- Form -----------------------------------------------------------------

def test_childpage_ist_unveraenderlich():
    seite = ChildPage(nodes=(), total=0, offset=0)
    with pytest.raises(AttributeError):
        seite.total = 1  # type: ignore[misc]


def test_childpage_repr_nennt_die_zahlen():
    """Englisch, wie die ganze Bibliothek -- bis zum Audit MNT-23-2
    (23.09.2026) stand hier "0 von 42, ab 10"."""
    assert repr(ChildPage(nodes=(), total=42, offset=10)) == \
        "ChildPage(0 of 42, from 10)"


async def test_ein_nicht_angekommener_titel_wird_gemeldet():
    """Der PUT antwortet leer -- ohne Rueckleseprobe waere ein verworfener
    Titel ein Erfolg."""
    from edusharing.errors import SilentDropError

    class Taub(Instanz):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.method == "PUT" and "/collection" in request.url.path:
                self.anfragen.append(request)
                return httpx.Response(200, content=b"")
            return super().handler(request)

    instanz = Taub()
    async with instanz.repo() as repo:
        with pytest.raises(SilentDropError) as fehler:
            await repo.collections.update("s-1", title="Neu",
                                          description="Auch neu")
    assert "cm:title" in fehler.value.dropped
    assert "cm:description" in fehler.value.dropped


# --- COR-1: zwei Zustands-Schreibstellen (Review 06.09.2026, F5/F6) ----------

def _bricht_beim_ersten(instanz: Instanz, methode: str, pfadende: str) -> list:
    """Der erste Aufruf dieser Methode auf diesen Pfad bricht nach dem Senden ab."""
    abgebrochen: list[int] = []
    echt = instanz.handler

    def handler(request):
        if (request.method == methode and request.url.path.endswith(pfadende)
                and not abgebrochen):
            abgebrochen.append(1)
            raise httpx.ReadTimeout("abgebrochen", request=request)
        return echt(request)

    instanz.handler = handler
    return abgebrochen


async def test_sammlung_aendern_wird_nach_abbruch_erneut_gesendet():
    instanz = Instanz()
    abgebrochen = _bricht_beim_ersten(instanz, "PUT", "/s-1")
    async with instanz.repo() as repo:
        knoten = await repo.collections.update("s-1", title="Neu")
    assert abgebrochen == [1]
    assert knoten.title == "Neu"


async def test_vorschaubild_wird_nach_abbruch_erneut_gesendet():
    """Ein Vorschaubild setzen ersetzt es -- zweimal angekommen ist derselbe
    Zustand (F5: die Stelle war nicht markiert)."""
    instanz = Instanz()
    abgebrochen = _bricht_beim_ersten(instanz, "POST", "/preview")
    async with instanz.repo() as repo:
        knoten = await repo.node(NID)
        await knoten.content.set_preview(PNG)
    assert abgebrochen == [1]
    assert instanz.eigenes_bild


async def test_eine_sammlung_ohne_titel_bekommt_beim_beschreiben_keinen():
    """Seit die Titelkette vereinheitlicht ist, faellt ``Node.title`` auf
    ``cm:name`` zurueck. Wer nur die Beschreibung aendert, darf davon aber
    keinen Titel geschrieben bekommen -- das waere ein Schreibvorgang, den
    niemand verlangt hat (Review 08.09.2026, Nebenwirkung von MNT-1)."""
    instanz = Instanz()
    instanz.sammlung["titel"] = ""
    instanz.sammlung["name"] = "Meine-Sammlung"
    async with instanz.repo() as repo:
        await repo.collections.update("s-1", description="Neuer Text")
    koerper = json.loads(instanz.letzte("PUT", "/collection").content)
    assert koerper["title"] == "", f"der Name waere hier gelandet: {koerper['title']!r}"
    assert koerper["properties"]["cm:title"] == [""]


async def test_ein_vorhandener_titel_bleibt_beim_beschreiben_stehen():
    """Die Gegenprobe: was da ist, wird erhalten."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        await repo.collections.update("s-1", description="Neuer Text")
    koerper = json.loads(instanz.letzte("PUT", "/collection").content)
    assert koerper["title"] == "Alt"
