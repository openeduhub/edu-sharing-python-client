"""Knoten lesen, anlegen, aendern -- mit Rueckleseprobe.

Gemessen gegen edu-sharing 11.0 (Staging, 27.08.2026), an einem Wegwerf-Knoten:

    PUT /metadata, Property im MDS          200  gespeichert
    PUT /metadata, Property NICHT im MDS    200  NICHT gespeichert
    POST /property, dieselbe Property       200  gespeichert
    PUT /metadata, erfundenes Feld          200  NICHT gespeichert

Zweimal HTTP 200 fuer etwas, das nicht passiert ist. Ein Statuscode ist hier
also kein Persistenzbeweis, und ohne Rueckleseprobe meldet eine Anwendung
Erfolg fuer verlorene Daten.
"""

import json

import httpx
import pytest

from edusharing.errors import (
    ContentTooLargeError,
    PermissionDeniedError,
    SilentDropError,
    ValidationError,
)
from edusharing.nodes import Node, Nodes
from edusharing.transport import Transport

REPO = "https://repositorium.example.test/edu-sharing"
NID = "c2eac649-8e3d-4ed2-aac6-498e3d7ed2d9"


def _node_antwort(properties: dict) -> dict:
    return {"node": {
        "ref": {"id": NID, "repo": "local"},
        "name": (properties.get("cm:name") or ["material.txt"])[0],
        "title": (properties.get("cclom:title") or [""])[0],
        "type": "ccm:io",
        "access": ["Read", "Write", "Delete"],
        "properties": properties,
    }}


class Server:
    """Ein Knoten im Speicher, der sich verhaelt wie edu-sharing.

    ``stumm`` nennt die Properties, die verworfen werden -- beim Aendern wie
    beim Anlegen, so wie das Repositorium alles verwirft, was der Metadatensatz
    nicht kennt oder selbst ableitet.
    """

    def __init__(self, properties: dict | None = None, stumm: tuple[str, ...] = (),
                 behaelt: tuple[str, ...] = (), umbenennung: bool = False):
        self.props = dict(properties or {"cclom:title": ["Alt"]})
        self.stumm = stumm
        self.behaelt = behaelt            # Loeschungen, die 200 sagen und nichts tun
        self.umbenennung = umbenennung    # renameIfExists haengt einen Zaehler an
        self.aufrufe: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.aufrufe.append(request)
        pfad, methode = request.url.path, request.method

        if methode == "GET" and pfad.endswith("/metadata"):
            return httpx.Response(200, json=_node_antwort(self.props))

        if methode == "PUT" and pfad.endswith("/metadata"):
            for k, v in json.loads(request.content).items():
                if k not in self.stumm:          # stille Verwerfung nachbilden
                    self.props[k] = v
            return httpx.Response(200, json=_node_antwort(self.props))

        if methode == "POST" and pfad.endswith("/property"):
            prop = request.url.params.get("property")
            wert = json.loads(request.content)
            if wert is None:
                if prop not in self.behaelt:
                    self.props.pop(prop, None)
            else:
                self.props[prop] = wert          # umgeht die MDS-Filterung
            return httpx.Response(200, content=b"")

        if methode == "POST" and pfad.endswith("/children"):
            gesendet = json.loads(request.content)
            behalten = {k: v for k, v in gesendet.items() if k not in self.stumm}
            if self.umbenennung and "cm:name" in behalten:
                behalten["cm:name"] = [behalten["cm:name"][0] + "-1"]
            self.props.update(behalten)
            # Ein neuer Knoten traegt nur, was angekommen ist -- gemessen zeigt
            # die POST-Antwort den Verlust bereits.
            return httpx.Response(200, json=_node_antwort(behalten))

        if methode == "DELETE":
            return httpx.Response(200, content=b"")

        return httpx.Response(404, json={"error": "x", "message": f"{methode} {pfad}"})


def _fehler(name: str) -> dict[str, str]:
    return {"error": name, "message": "abgelehnt"}


def _nodes(server: Server) -> Nodes:
    transport = Transport(
        REPO, client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
        backoff_base=0.0,
    )
    return Nodes(transport)


# --- Lesen ----------------------------------------------------------------

async def test_knoten_laden():
    node = await _nodes(Server()).get(NID)
    assert isinstance(node, Node)
    assert node.id == NID
    assert node.title == "Alt"
    assert node.url == f"{REPO}/components/render/{NID}"


async def test_geladener_knoten_kennt_seine_rechte():
    """Vor einem Schreibvorgang laesst sich damit pruefen, ob er ueberhaupt
    erlaubt ist -- statt ein stilles Nichts als Erfolg zu lesen."""
    node = await _nodes(Server()).get(NID)
    assert node.can_write is True
    assert "Delete" in node.access


async def test_properties_sind_erreichbar():
    node = await _nodes(Server({"cclom:title": ["Alt"], "ccm:wwwurl": ["https://x.test"]})).get(NID)
    assert node.get("ccm:wwwurl") == "https://x.test"
    assert node.get_all("ccm:wwwurl") == ["https://x.test"]
    assert node.get("gibtsnicht") is None


# --- Schreiben mit Rueckleseprobe -----------------------------------------

async def test_update_speichert_und_liest_zurueck():
    server = Server()
    node = await _nodes(server).get(NID)
    aktualisiert = await node.update(title="Neu")
    assert aktualisiert.title == "Neu"
    assert any(r.method == "PUT" for r in server.aufrufe)


async def test_update_prueft_wirklich_zurueck():
    """Die Probe muss ein echter GET nach dem Schreiben sein -- die Antwort des
    PUT selbst zu glauben hiesse, dem Server bei der Frage zu trauen, die er
    gerade falsch beantwortet."""
    server = Server()
    node = await _nodes(server).get(NID)
    server.aufrufe.clear()
    await node.update(title="Neu")
    folge = [r.method for r in server.aufrufe]
    assert folge.index("PUT") < folge.index("GET"), "GET muss nach dem PUT kommen"


async def test_stiller_verlust_wird_zum_fehler():
    """Der Kernfall: HTTP 200, Wert nach der Rueckleseprobe abwesend."""
    server = Server(stumm=("ccm:oeh_collection_compendium_text",))
    node = await _nodes(server).get(NID)
    with pytest.raises(SilentDropError) as info:
        await node.update(properties={"ccm:oeh_collection_compendium_text": "Text"})
    assert "ccm:oeh_collection_compendium_text" in str(info.value)


async def test_fehler_nennt_den_ausweg():
    """Wer hier strandet, soll nicht raten muessen: set_property umgeht die
    Filterung des Metadatensatzes."""
    server = Server(stumm=("ccm:foo",))
    node = await _nodes(server).get(NID)
    with pytest.raises(SilentDropError) as info:
        await node.update(properties={"ccm:foo": "x"})
    assert "set_property" in str(info.value)


async def test_fehler_kennt_die_betroffenen_felder():
    server = Server(stumm=("ccm:foo", "ccm:bar"))
    node = await _nodes(server).get(NID)
    with pytest.raises(SilentDropError) as info:
        await node.update(properties={"ccm:foo": "x", "ccm:bar": "y", "cclom:title": "ok"})
    assert set(info.value.dropped) == {"ccm:foo", "ccm:bar"}


async def test_teilerfolg_bleibt_erhalten():
    """Was durchkam, bleibt geschrieben -- edu-sharing kann nicht zurueckrollen.
    Der Fehler meldet den Verlust, taeuscht aber keinen Rollback vor."""
    server = Server(stumm=("ccm:foo",))
    node = await _nodes(server).get(NID)
    with pytest.raises(SilentDropError):
        await node.update(properties={"ccm:foo": "x", "cclom:title": "Durchgekommen"})
    assert server.props["cclom:title"] == ["Durchgekommen"]


async def test_verify_abschaltbar():
    """Bei einem Stapellauf ueber viele Knoten verdoppelt die Probe die
    Aufrufe. Wer das abwaegt, darf sie abschalten -- bewusst, nicht by default."""
    server = Server(stumm=("ccm:foo",))
    node = await _nodes(server).get(NID)
    await node.update(properties={"ccm:foo": "x"}, verify=False)
    assert not any(r.method == "GET" for r in server.aufrufe[1:])


# --- Der Direktweg --------------------------------------------------------

class _Abbruch(Server):
    """Der erste Aufruf der genannten Methode bricht nach dem Senden ab."""

    def __init__(self, methode: str):
        super().__init__()
        self.methode = methode
        self.abgebrochen = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == self.methode and not self.abgebrochen:
            self.abgebrochen += 1
            raise httpx.ReadTimeout("abgebrochen", request=request)
        return super().__call__(request)


async def test_update_wird_nach_abbruch_wiederholt():
    """Metadaten ersetzen ist idempotent: doppelt angekommen ist derselbe
    Zustand. Das Update sagt es dem Transport -- sonst bliebe es beim ersten
    Abbruch stehen, wo ein Anlegen stehen bleiben muss (COR-1)."""
    server = _Abbruch("PUT")
    node = await _nodes(server).get(NID)

    await node.update(title="Neu")

    assert server.abgebrochen == 1
    assert server.props["cclom:title"] == ["Neu"]


async def test_set_property_wird_nach_abbruch_wiederholt():
    server = _Abbruch("POST")
    node = await _nodes(server).get(NID)

    await node.set_property("ccm:custom", ["x"])

    assert server.abgebrochen == 1
    assert server.props["ccm:custom"] == ["x"]


async def test_set_property_umgeht_die_filterung():
    server = Server(stumm=("ccm:foo",))
    node = await _nodes(server).get(NID)
    aktualisiert = await node.set_property("ccm:foo", "x")
    assert aktualisiert.get("ccm:foo") == "x"


async def test_set_property_prueft_ebenfalls_zurueck():
    """Auch dieser Weg kann scheitern -- etwa mangels Schreibrecht."""
    class Verweigert(Server):
        def __call__(self, request):
            if request.method == "POST" and request.url.path.endswith("/property"):
                self.aufrufe.append(request)
                return httpx.Response(200, content=b"")   # tut nur so
            return super().__call__(request)

    node = await _nodes(Verweigert()).get(NID)
    with pytest.raises(SilentDropError):
        await node.set_property("ccm:foo", "x")


async def test_set_property_kann_loeschen():
    server = Server({"cclom:title": ["Alt"], "ccm:foo": ["weg damit"]})
    node = await _nodes(server).get(NID)
    aktualisiert = await node.set_property("ccm:foo", None)
    assert aktualisiert.get("ccm:foo") is None


async def test_set_property_none_prueft_die_loeschung_nach():
    """Gemessen ist nur, dass "null" loescht. Eine Instanz, die 200 sagt und die
    Eigenschaft behaelt, darf nicht als geloescht gelten -- sonst waere die
    Rueckleseprobe hier eine Anfrage fuer nichts."""
    server = Server({"cclom:title": ["Alt"], "ccm:foo": ["bleibt"]}, behaelt=("ccm:foo",))
    node = await _nodes(server).get(NID)
    with pytest.raises(SilentDropError) as fehler:
        await node.set_property("ccm:foo", None)
    assert "ccm:foo" in str(fehler.value) and fehler.value.dropped == ["ccm:foo"]


# --- Feld-Aliase ----------------------------------------------------------

async def test_titel_wird_in_beide_namensraeume_geschrieben():
    """Gemessen im WLO-Umfeld: die Oberflaeche rendert cm:title und
    cclom:title unterschiedlich. Nur eines zu setzen fuehrt dazu, dass die
    Anzeige etwas anderes zeigt als die Anwendung geschrieben hat."""
    server = Server()
    node = await _nodes(server).get(NID)
    await node.update(title="Neu")
    assert server.props["cm:title"] == ["Neu"]
    assert server.props["cclom:title"] == ["Neu"]


async def test_beschreibung_ebenfalls_doppelt():
    server = Server()
    node = await _nodes(server).get(NID)
    await node.update(description="Text")
    assert server.props["cm:description"] == ["Text"]
    assert server.props["cclom:general_description"] == ["Text"]


async def test_unbekannter_alias_wird_abgelehnt():
    node = await _nodes(Server()).get(NID)
    with pytest.raises(Exception, match="voelligNeu"):
        await node.update(voelligNeu="x")


async def test_werte_werden_zu_listen():
    """edu-sharing erwartet jede Property als Liste, auch einzelne Werte."""
    server = Server()
    node = await _nodes(server).get(NID)
    await node.update(properties={"ccm:wwwurl": "https://x.test"})
    assert server.props["ccm:wwwurl"] == ["https://x.test"]


# --- Anlegen und Loeschen -------------------------------------------------

async def test_knoten_anlegen():
    server = Server()
    node = await _nodes(server).create("parent-1", name="neu.txt", title="Frisch")
    assert node.id == NID
    erzeugung = next(r for r in server.aufrufe if r.url.path.endswith("/children"))
    assert "parent-1" in str(erzeugung.url)
    assert erzeugung.url.params.get("type") == "ccm:io"


async def test_anlegen_ohne_namen_wird_abgelehnt():
    """cm:name ist der Schluessel im Elternknoten -- ohne ihn ist das Ergebnis
    vom Server abhaengig statt vorhersagbar."""
    with pytest.raises(Exception, match="name"):
        await _nodes(Server()).create("parent-1", name="")


async def test_loeschen_landet_per_vorgabe_im_papierkorb():
    """recycle=true ist der Schalter fuer Wiederherstellbarkeit und wird
    deshalb immer explizit gesetzt, nie dem Server ueberlassen."""
    server = Server()
    node = await _nodes(server).get(NID)
    await node.delete()
    loeschung = next(r for r in server.aufrufe if r.method == "DELETE")
    assert loeschung.url.params.get("recycle") == "true"


async def test_endgueltiges_loeschen_muss_verlangt_werden():
    server = Server()
    node = await _nodes(server).get(NID)
    await node.delete(recycle=False)
    loeschung = next(r for r in server.aufrufe if r.method == "DELETE")
    assert loeschung.url.params.get("recycle") == "false"


# --- Der synchrone Zugang -------------------------------------------------

def test_synchroner_knoten_blockiert_statt_zu_awaiten():
    """Wer Repository benutzt, soll node.update() ohne await schreiben koennen
    -- sonst ist der synchrone Zugang beim Schreiben eine Sackgasse."""
    from edusharing import Repository

    server = Server()
    with Repository(
        REPO, client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
    ) as repo:
        node = repo.node(NID)
        assert node.title == "Alt"
        aktualisiert = node.update(title="Neu")
        assert aktualisiert.title == "Neu"


def test_synchroner_knoten_meldet_stillen_verlust():
    from edusharing import Repository

    server = Server(stumm=("ccm:foo",))
    with Repository(
        REPO, client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
    ) as repo:
        with pytest.raises(SilentDropError):
            repo.node(NID).update(properties={"ccm:foo": "x"})


def test_synchron_anlegen_und_loeschen():
    from edusharing import Repository

    server = Server()
    with Repository(
        REPO, client=httpx.AsyncClient(transport=httpx.MockTransport(server)),
    ) as repo:
        node = repo.create_node("parent-1", name="neu.txt")
        assert node.id == NID
        node.delete()
        assert any(r.method == "DELETE" for r in server.aufrufe)


# --- Schlagworte: eine geteilte Liste -------------------------------------

async def test_schlagworte_werden_gelesen():
    server = Server({"cclom:general_keyword": ["Weimar", "Klassik"]})
    node = await _nodes(server).get(NID)
    assert node.keywords == ["Weimar", "Klassik"]


async def test_hinzufuegen_erhaelt_fremde_eintraege():
    """cclom:general_keyword pflegen mehrere Beteiligte gemeinsam. Wer die
    Liste setzt statt ergaenzt, loescht die Arbeit anderer -- lautlos."""
    server = Server({"cclom:general_keyword": ["Fremd", "Auch fremd"]})
    node = await _nodes(server).get(NID)
    aktualisiert = await node.add_keywords("Meins")
    assert aktualisiert.keywords == ["Fremd", "Auch fremd", "Meins"]


async def test_hinzufuegen_dupliziert_nicht():
    server = Server({"cclom:general_keyword": ["Weimar"]})
    node = await _nodes(server).get(NID)
    aktualisiert = await node.add_keywords("Weimar", "Klassik")
    assert aktualisiert.keywords == ["Weimar", "Klassik"]


async def test_hinzufuegen_liest_vorher_frisch():
    """Das Node-Objekt kann veraltet sein. Auf seinem Stand zu mergen wuerde
    alles ueberschreiben, was seit dem Laden dazugekommen ist."""
    server = Server({"cclom:general_keyword": ["Alt"]})
    node = await _nodes(server).get(NID)
    server.props["cclom:general_keyword"] = ["Alt", "Inzwischen dazugekommen"]
    aktualisiert = await node.add_keywords("Meins")
    assert "Inzwischen dazugekommen" in aktualisiert.keywords


async def test_entfernen_laesst_andere_stehen():
    server = Server({"cclom:general_keyword": ["Fremd", "Meins"]})
    node = await _nodes(server).get(NID)
    aktualisiert = await node.remove_keywords("Meins")
    assert aktualisiert.keywords == ["Fremd"]


async def test_entfernen_eines_unbekannten_ist_kein_fehler():
    server = Server({"cclom:general_keyword": ["Fremd"]})
    node = await _nodes(server).get(NID)
    aktualisiert = await node.remove_keywords("gibtsnicht")
    assert aktualisiert.keywords == ["Fremd"]


async def test_hinzufuegen_ohne_argumente_schreibt_nicht():
    """Ein leerer Aufruf darf keinen Schreibvorgang ausloesen."""
    server = Server({"cclom:general_keyword": ["Fremd"]})
    node = await _nodes(server).get(NID)
    server.aufrufe.clear()
    await node.add_keywords()
    assert not any(r.method == "PUT" for r in server.aufrufe)


# --- Dateien --------------------------------------------------------------

async def test_datei_hochladen():
    """mimetype ist Pflicht -- die Spec deklariert ihn als required, und ohne
    ihn kann das Repositorium den Inhalt nicht einordnen."""
    hochgeladen = []

    class MitDatei(Server):
        def __call__(self, request):
            if request.method == "POST" and request.url.path.endswith("/content"):
                hochgeladen.append(request)
                return httpx.Response(200, json=_node_antwort(self.props))
            return super().__call__(request)

    node = await _nodes(MitDatei()).get(NID)
    await node.content.upload(b"Hallo", filename="probe.txt", mimetype="text/plain")
    assert hochgeladen
    assert hochgeladen[0].url.params.get("mimetype") == "text/plain"


async def test_upload_ohne_mimetype_wird_abgelehnt():
    node = await _nodes(Server()).get(NID)
    with pytest.raises(Exception, match="mimetype"):
        await node.content.upload(b"x", filename="p.txt", mimetype="")


async def test_download_nutzt_die_downloadurl_des_knotens():
    """Es gibt kein GET auf .../content -- gemessen antwortet es mit 405.
    Der Weg fuehrt ueber die downloadUrl aus den Metadaten."""
    geholt = []

    class MitDownload(Server):
        def __call__(self, request):
            if "eduservlet/download" in str(request.url):
                geholt.append(request)
                return httpx.Response(200, content=b"Dateiinhalt")
            return super().__call__(request)

    server = MitDownload()
    node = await _nodes(server).get(NID)
    node._data["downloadUrl"] = f"{REPO}/eduservlet/download?node={NID}"
    node._data["content"] = {"hash": "-1222810457"}     # gemessene Form
    assert await node.content.download() == b"Dateiinhalt"
    assert geholt


async def test_download_ohne_datei_meldet_das_klar():
    """Ein Knoten ohne Datei darf keinen leeren Bytestring vortaeuschen.

    Die Pruefung geht ueber den Hash, nicht ueber downloadUrl: gemessen ist
    downloadUrl IMMER gesetzt, und ein Knoten ohne Inhalt liefert daran 200
    mit null Bytes. Der Hash dagegen ist nur ohne Inhalt None -- bei einer
    0-Byte-Datei ist er gesetzt.
    """
    node = await _nodes(Server()).get(NID)
    node._data["downloadUrl"] = f"{REPO}/eduservlet/download?node={NID}"
    node._data["content"] = {"hash": None}
    assert node.content.has_content is False
    with pytest.raises(Exception, match="carries no file"):
        await node.content.download()


async def test_download_lehnt_eine_zu_grosse_datei_vor_dem_abruf_ab():
    """Audit SEC-2: die Groesse steht in cclom:size -- wer sie kennt, muss die
    Datei nicht laden, um sie abzulehnen. Kein Abruf, ein Fehler mit beiden
    Zahlen; unter dem Deckel kommt die Datei wie immer."""
    geholt = []

    class MitDownload(Server):
        def __call__(self, request):
            if "eduservlet/download" in str(request.url):
                geholt.append(request)
                return httpx.Response(200, content=b"x" * 50)
            return super().__call__(request)

    node = await _nodes(MitDownload()).get(NID)
    node._data["downloadUrl"] = f"{REPO}/eduservlet/download?node={NID}"
    node._data["content"] = {"hash": "-1222810457"}
    node._data["properties"]["cclom:size"] = ["50"]
    with pytest.raises(ContentTooLargeError, match="50"):
        await node.content.download(max_bytes=10)
    assert geholt == []
    assert await node.content.download(max_bytes=50) == b"x" * 50


async def test_eine_unlesbare_groesse_haelt_den_abruf_nicht_auf():
    """Audit COR-23-5 (23.09.2026): ``"²".isdigit()`` ist wahr, ``int("²")``
    wirft -- ``cclom:size = ["²"]`` liess ``download(max_bytes=...)`` mit
    ``ValueError`` enden. Eine unlesbare Groesse ist keine Groesse; dann
    entscheidet, was ankommt."""

    class MitDownload(Server):
        def __call__(self, request):
            if "eduservlet/download" in str(request.url):
                return httpx.Response(200, content=b"x" * 50)
            return super().__call__(request)

    node = await _nodes(MitDownload()).get(NID)
    node._data["downloadUrl"] = f"{REPO}/eduservlet/download?node={NID}"
    node._data["content"] = {"hash": "-1222810457"}
    node._data["properties"]["cclom:size"] = ["²"]
    assert node.content.size is None
    assert await node.content.download(max_bytes=50) == b"x" * 50
    with pytest.raises(ContentTooLargeError):
        await node.content.download(max_bytes=10)


async def test_leere_datei_gilt_als_inhalt():
    """Die Unterscheidung, die den Hash noetig macht: eine 0-Byte-Datei ist
    ein Inhalt, ein Knoten ohne Datei nicht -- beide haben cclom:size None."""
    node = await _nodes(Server()).get(NID)
    node._data["content"] = {"hash": "-190212752"}     # gemessen bei b""
    assert node.content.has_content is True


async def test_textinhalt_wird_ausgepackt():
    """textContent antwortet mit {"text": ...} -- der Rumpf ist JSON, nicht
    der Text selbst."""
    class MitText(Server):
        def __call__(self, request):
            if request.url.path.endswith("/textContent"):
                return httpx.Response(200, json={"text": "Der extrahierte Text"})
            return super().__call__(request)

    node = await _nodes(MitText()).get(NID)
    assert await node.content.text() == "Der extrahierte Text"


# --- Rueckleseprobe beim Anlegen ------------------------------------------

async def test_anlegen_meldet_ein_verschlucktes_feld():
    """Bis zum 28.08.2026 prueste nur update() und set_property() nach, nicht
    create(). Damit war ausgerechnet der erste Schreibvorgang der einzige ohne
    Schutz vor stillem Verlust.

    Gemessen gegen Staging: ein Anlegen mit ccm:oeh_lrt_aggregated meldet HTTP
    200, und das Feld fehlt in der Antwort -- das Repositorium leitet es aus
    ccm:oeh_lrt ab und nimmt es nicht entgegen. Die Antwort zeigt den Verlust
    also bereits; die Pruefung kostet keine zusaetzliche Anfrage.
    """
    server = Server(stumm=("ccm:oeh_lrt_aggregated",))
    with pytest.raises(SilentDropError) as fehler:
        await _nodes(server).create(
            "eltern", name="x.txt",
            properties={"ccm:oeh_lrt_aggregated": ["http://x/video"]})
    assert "ccm:oeh_lrt_aggregated" in str(fehler.value)


async def test_anlegen_ohne_pruefung_bleibt_moeglich():
    """Wer weiss, dass ein Feld abgeleitet wird, soll es mitschicken duerfen."""
    server = Server(stumm=("ccm:oeh_lrt_aggregated",))
    node = await _nodes(server).create(
        "eltern", name="x.txt", verify=False,
        properties={"ccm:oeh_lrt_aggregated": ["http://x/video"]})
    assert node.id == NID


async def test_anlegen_mit_umbenennung_ist_kein_verlust():
    """renameIfExists loest eine Namenskollision mit einem Zaehler. Der neue
    cm:name weicht dann vom gesendeten ab -- das Repositorium haelt sein
    Versprechen, es verwirft nichts. Bis heute meldete die Probe das als
    stillen Verlust, mit falscher Diagnose."""
    server = Server(umbenennung=True)
    node = await _nodes(server).create("eltern", name="x.txt", title="T")
    assert node.name != "x.txt" and node.get("cm:name") == node.name, (
        "der gespeicherte Name ist der Schluessel, den das Repositorium waehlte")


async def test_anlegen_prueft_ohne_zusaetzliche_anfrage():
    """Die POST-Antwort traegt den angelegten Knoten -- ein zweiter Zugriff
    waere Verschwendung."""
    server = Server()
    await _nodes(server).create("eltern", name="x.txt", title="T")
    assert len(server.aufrufe) == 1, f"{len(server.aufrufe)} Anfragen statt einer"


def test_node_liefert_lesbare_vokabularwerte():
    """``labels`` gab es nur an SearchHit, nicht an Node.

    Wer einen Treffer in der Hand hielt, bekam 'Biologie'; wer denselben Knoten
    ueber ``repo.node(id)`` holte, bekam die URI und musste die
    _DISPLAYNAME-Konvention kennen. Dieselbe Frage, zwei Antworten -- aufgefallen
    beim Durchtesten von ccm:oeh_extendedType am 28.08.2026, wo genau dieser
    Weg gebraucht wurde.
    """
    node = Node({"ref": {"id": "n1"}, "properties": {
        "ccm:taxonid": ["http://w3id.org/openeduhub/vocabs/discipline/080"],
        "ccm:taxonid_DISPLAYNAME": ["Biologie"],
    }}, None)
    assert node.labels("ccm:taxonid") == ["Biologie"]


def test_node_ohne_lesbare_werte_gibt_eine_leere_liste():
    """Nicht jede Property fuehrt ein Vokabular -- das ist kein Fehler."""
    node = Node({"ref": {"id": "n1"}, "properties": {"cclom:title": ["Titel"]}}, None)
    assert node.labels("cclom:title") == []


# --- Referenz oder Original? ----------------------------------------------
#
# Eine Sammlung haelt Referenzen, nicht Datensaetze. Ein Listing liefert die
# IDs der Referenzen -- und das ist der gewoehnliche Weg zu einer ID, kein
# Sonderfall. Gemessen gegen Staging am 02.09.2026: das DTO einer Referenz
# traegt ``originalId`` und ``ccm:original`` zeigt aufs Original; auf einem
# Original FEHLT ``originalId`` und ``ccm:original`` zeigt auf den Knoten
# selbst (3/3, auch vom MCP am 17.08. so gemessen).

REFERENZ = {"ref": {"id": "r-1"}, "originalId": "o-1",
            "aspects": ["ccm:collection_io_reference", "ccm:iometadata"],
            "properties": {"ccm:original": ["o-1"], "cclom:title": ["T"]}}
ORIGINAL = {"ref": {"id": "o-1"},
            "aspects": ["ccm:iometadata"],
            "properties": {"ccm:original": ["o-1"], "cclom:title": ["T"]}}


def test_eine_referenz_kennt_ihr_original():
    node = Node(REFERENZ, None)
    assert node.original_id == "o-1"
    assert node.is_reference is True
    assert node.aspects == ("ccm:collection_io_reference", "ccm:iometadata")


def test_ein_original_ist_keine_referenz_auf_sich_selbst():
    """Wer ``ccm:original`` ohne Selbstvergleich liest, meldet jeden Datensatz
    als Referenz auf sich selbst."""
    node = Node(ORIGINAL, None)
    assert node.original_id is None
    assert node.is_reference is False


def test_ohne_originalid_zaehlt_die_eigenschaft_wenn_sie_abweicht():
    """Aeltere Instanzen ohne ``originalId`` im DTO: die Eigenschaft ist der
    Rueckfall -- nur, wenn sie nicht auf den Knoten selbst zeigt."""
    alt = {"ref": {"id": "r-2"}, "properties": {"ccm:original": ["o-2"]}}
    assert Node(alt, None).original_id == "o-2"
    assert Node({"ref": {"id": "x"}, "properties": {}}, None).aspects == ()


# --- Schreiben an einer Referenz ------------------------------------------
#
# Vom MCP am 17.08.2026 gegen Staging gemessen (services/write/nodes.ts):
# ein PUT an eine Referenz wird AUF DER REFERENZ gespeichert, erreicht das
# Original nie, und die Referenz hoert ab dann auf zu erben. Die Rueckleseprobe
# bemerkt das nicht -- sie liest denselben Knoten und findet genau den Wert,
# den sie geschrieben hat. Darum geht jeder Schreibvorgang ans Original und
# sagt es (``redirected_from``). Loeschen dagegen nicht: an einer Referenz
# entfernt es nur die Referenz, und eine Umleitung waere genau der
# Datenverlust, den die Umleitung beim Schreiben verhindern soll (MCP, F10).

REF, ORIG = "r-1", "o-1"


class ZweiKnoten:
    """Referenz ``r-1`` auf Original ``o-1``, beide mit eigenem Zustand."""

    def __init__(self) -> None:
        self.props = {REF: {"cclom:title": ["Alt"], "ccm:original": [ORIG]},
                      ORIG: {"cclom:title": ["Alt"], "ccm:original": [ORIG]}}
        self.aufrufe: list[httpx.Request] = []

    def _antwort(self, nid: str) -> dict:
        data = _node_antwort(self.props[nid])["node"]
        data["ref"]["id"] = nid
        if nid == REF:
            data["originalId"] = ORIG
            data["aspects"] = ["ccm:collection_io_reference"]
        return {"node": data}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.aufrufe.append(request)
        pfad, methode = request.url.path, request.method
        nid = REF if f"/{REF}" in pfad else ORIG
        if methode == "GET" and pfad.endswith("/metadata"):
            return httpx.Response(200, json=self._antwort(nid))
        if methode == "PUT" and pfad.endswith("/metadata"):
            self.props[nid].update(json.loads(request.content))
            return httpx.Response(200, json=self._antwort(nid))
        if methode == "POST" and pfad.endswith("/property"):
            self.props[nid][request.url.params["property"]] = json.loads(request.content)
            return httpx.Response(200, content=b"")
        if methode == "DELETE":
            return httpx.Response(200, content=b"")
        return httpx.Response(404, json={"error": "x", "message": pfad})

    def pfade(self, methode: str) -> list[str]:
        return [r.url.path for r in self.aufrufe if r.method == methode]


async def test_update_an_einer_referenz_schreibt_ans_original():
    server = ZweiKnoten()
    node = await _nodes(server).get(REF)
    neu = await node.update(title="Neu")
    assert server.pfade("PUT") == [f"/edu-sharing/rest/node/v1/nodes/-home-/{ORIG}/metadata"]
    assert neu.id == ORIG
    assert neu.redirected_from == REF
    assert server.props[ORIG]["cclom:title"] == ["Neu"]
    assert server.props[REF]["cclom:title"] == ["Alt"]


async def test_update_an_einem_original_leitet_nicht_um():
    server = ZweiKnoten()
    node = await _nodes(server).get(ORIG)
    neu = await node.update(title="Neu")
    assert neu.id == ORIG
    assert neu.redirected_from is None


async def test_set_property_an_einer_referenz_schreibt_ans_original():
    server = ZweiKnoten()
    node = await _nodes(server).get(REF)
    neu = await node.set_property("ccm:foo", "x")
    assert server.pfade("POST") == [f"/edu-sharing/rest/node/v1/nodes/-home-/{ORIG}/property"]
    assert neu.id == ORIG
    assert neu.redirected_from == REF


async def test_add_keywords_an_einer_referenz_mischt_die_des_originals():
    server = ZweiKnoten()
    server.props[ORIG]["cclom:general_keyword"] = ["bleibt"]
    node = await _nodes(server).get(REF)
    neu = await node.add_keywords("neu")
    assert server.props[ORIG]["cclom:general_keyword"] == ["bleibt", "neu"]
    assert neu.id == ORIG


async def test_loeschen_an_einer_referenz_wird_nicht_umgeleitet():
    server = ZweiKnoten()
    node = await _nodes(server).get(REF)
    await node.delete()
    assert server.pfade("DELETE") == [f"/edu-sharing/rest/node/v1/nodes/-home-/{REF}"]


async def test_ohne_probe_weist_eine_umleitung_trotzdem_das_original_aus():
    """verify=False spart die Probe, nicht die Auskunft: wer an eine Referenz
    schreibt, bekommt das Original zurueck -- gestempelt."""
    server = ZweiKnoten()
    node = await _nodes(server).get(REF)
    neu = await node.update(title="Neu", verify=False)
    assert neu.id == ORIG and neu.redirected_from == REF
    assert server.props[ORIG]["cclom:title"] == ["Neu"]
    assert len(server.pfade("GET")) == 2, "einmal laden, einmal das Original lesen"


async def test_ohne_probe_und_ohne_umleitung_wird_nicht_gelesen():
    server = ZweiKnoten()
    node = await _nodes(server).get(ORIG)
    neu = await node.update(title="Neu", verify=False)
    assert neu is node and len(server.pfade("GET")) == 1


async def test_ein_fehler_des_originals_nennt_die_umleitung():
    """Der Aufrufer hatte die ID der Referenz; ein 403 des Originals nennt eine
    URL, die er nie benutzt hat. Die Notiz stellt den Zusammenhang her."""
    class Verweigert(ZweiKnoten):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if request.method == "PUT" and f"/{ORIG}/" in request.url.path:
                self.aufrufe.append(request)
                return httpx.Response(403, json=_fehler("DAOSecurityException"))
            return super().__call__(request)

    node = await _nodes(Verweigert()).get(REF)
    with pytest.raises(PermissionDeniedError) as fehler:
        await node.update(title="Neu")
    assert any(REF in note and ORIG in note for note in fehler.value.__notes__)


# --- Auch ein Treffer kennt sein Original -----------------------------------

def test_ein_treffer_kennt_sein_original():
    from edusharing.results import SearchHit
    ref = SearchHit.from_node({"ref": {"id": "r-1"}, "originalId": "o-1", "properties": {}}, REPO)
    orig = SearchHit.from_node({"ref": {"id": "o-1"},
                                "properties": {"ccm:original": ["o-1"]}}, REPO)
    assert ref.original_id == "o-1"
    assert orig.original_id is None


def test_hit_as_dict_nennt_das_original():
    from edusharing.flows.serialize import hit_as_dict
    from edusharing.results import SearchHit
    hit = SearchHit.from_node({"ref": {"id": "r-1"}, "originalId": "o-1", "properties": {}}, REPO)
    assert hit_as_dict(hit, {})["original_id"] == "o-1"


# --- SEC-7: der mimetype landet in einer Kopfzeile -------------------------
#
# httpx schreibt ``Content-Type: <mimetype>`` in den Teilabschnitt, ohne den
# Wert zu pruefen -- gemessen mit httpx 0.28.1 am 08.09.2026:
#
#     files={"file": ("n.pdf", b"xy", "application/pdf\r\nX-Injected: ja")}
#
# ergibt zwei Kopfzeilen statt einer. Den Dateinamen kodiert httpx (``%0D%0A``),
# den Inhaltstyp nicht. Was ein Server aus einer zweiten Kopfzeile macht, ist
# seine Sache -- die Bibliothek darf sie gar nicht erst schreiben.

BOESE = [
    # Der Fall, den die erste Fassung durchliess: ``re.match`` mit ``$``
    # akzeptiert einen abschliessenden Zeilenumbruch (Pruefung 08.09.2026).
    # Ein blankes LF im Kopfzeilenblock beendet fuer einen toleranten Parser
    # die Kopfzeilen -- genau die Klasse, gegen die diese Wache steht.
    "application/pdf\n",
    "application/pdf\r\n",
    "application/pdf\r\nX-Injected: ja",
    "application/pdf\nX-Injected: ja",
    "application/pdf\r\n\r\nkoerper",
    "application/pdf; charset=\"a\r\nb\"",
    "text/plain\x00",
]


@pytest.mark.parametrize("mimetype", BOESE)
async def test_ein_mimetype_der_eine_kopfzeile_faelscht_wird_abgelehnt(mimetype):
    node = await _nodes(Server()).get(NID)
    with pytest.raises(ValidationError, match="mimetype"):
        await node.content.upload(b"x", filename="p.txt", mimetype=mimetype)


@pytest.mark.parametrize("mimetype", BOESE)
async def test_auch_das_vorschaubild_prueft_seinen_mimetype(mimetype):
    """Derselbe Weg, dieselbe Kopfzeile -- eine Wache an einer der beiden
    Stellen ist keine."""
    node = await _nodes(Server()).get(NID)
    with pytest.raises(ValidationError, match="mimetype"):
        await node.content.set_preview(b"x", mimetype=mimetype)


@pytest.mark.parametrize("mimetype", [
    "application/pdf",
    "image/png",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/x-tar",
    "audio/mp4",
    "application/vnd.oasis.opendocument.text",
])
async def test_gewoehnliche_typen_gehen_durch(mimetype):
    """Gegenprobe. Die Regel darf nichts treffen, was in einem Bestand
    vorkommt -- die langen Office-Typen sind der Ernstfall."""
    class MitDatei(Server):
        def __call__(self, request):
            if request.method == "POST" and request.url.path.endswith("/content"):
                return httpx.Response(200, json=_node_antwort({}))
            return super().__call__(request)

    node = await _nodes(MitDatei()).get(NID)
    await node.content.upload(b"x", filename="p", mimetype=mimetype)


async def test_ein_typ_mit_parameter_wird_benannt_nicht_nur_verweigert():
    """``text/plain; charset=utf-8`` ist eine gueltige Kopfzeile, aber nicht
    das, was das Repositorium als Klassifizierung erwartet -- es bekommt den
    Wert auch als Abfrageparameter. Wer ihn schickt, soll lesen warum."""
    node = await _nodes(Server()).get(NID)
    with pytest.raises(ValidationError, match=r"charset|parameter|type/subtype"):
        await node.content.upload(b"x", filename="p", mimetype="text/plain; charset=utf-8")


async def test_leere_schlagworte_werden_nicht_geschrieben():
    """``cclom:general_keyword`` ist eine geteilte Liste (Audit COR-8).

    Verglichen wurde gestrippt und kleingeschrieben, **gespeichert** aber der
    Rohwert -- und ein leerer String bestand den Vergleich, solange noch kein
    leerer darin stand. Gemessen im Bericht: ``add_keywords("", "   ",
    " Optik ")`` sendete ``['Physik', '', ' Optik ']``.

    Ein leeres Schlagwort ist in jeder Anzeige eine leere Zeile und in jeder
    Facette ein Eintrag ohne Namen -- und weil die Liste geteilt ist, sieht ihn
    jeder, der danach hineinschaut.
    """
    server = ZweiKnoten()
    server.props[ORIG]["cclom:general_keyword"] = ["Physik"]
    node = await _nodes(server).get(ORIG)
    await node.add_keywords("", "   ", " Optik ")
    assert server.props[ORIG]["cclom:general_keyword"] == ["Physik", "Optik"]


async def test_ein_schlagwort_das_es_schon_gibt_kommt_nicht_gepolstert_dazu():
    """`` Physik `` und ``physik`` sind dasselbe Schlagwort -- der Vergleich
    sah das schon, die Speicherung nicht."""
    server = ZweiKnoten()
    server.props[ORIG]["cclom:general_keyword"] = ["Physik"]
    node = await _nodes(server).get(ORIG)
    await node.add_keywords(" physik ")
    assert server.props[ORIG]["cclom:general_keyword"] == ["Physik"]


async def test_nur_leere_schlagworte_schreiben_gar_nichts():
    """Nichts hinzuzufuegen heisst nichts zu schreiben -- ein Schreibvorgang,
    der nichts aendert, kostet eine Anfrage und eine Version."""
    server = ZweiKnoten()
    server.props[ORIG]["cclom:general_keyword"] = ["Physik"]
    node = await _nodes(server).get(ORIG)
    await node.add_keywords("", "   ")
    assert server.props[ORIG]["cclom:general_keyword"] == ["Physik"]
    assert not server.pfade("POST"), "es gab nichts zu schreiben"


async def test_ein_gepolstertes_schlagwort_wird_beim_entfernen_erkannt():
    """Gegenprobe fuer die andere Richtung: das Entfernen strippt schon."""
    server = ZweiKnoten()
    server.props[ORIG]["cclom:general_keyword"] = ["Physik", "Optik"]
    node = await _nodes(server).get(ORIG)
    await node.remove_keywords("  optik  ")
    assert server.props[ORIG]["cclom:general_keyword"] == ["Physik"]
