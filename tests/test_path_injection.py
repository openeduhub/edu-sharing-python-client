"""Bezeichner duerfen den Pfad nicht verlassen.

Audit-Befund F1 vom 27.08.2026. Der Unit-Test in ``test_urls.py`` prueft, dass
``path_segment`` richtig kodiert. Diese Datei prueft das, was dort nicht
sichtbar waere: dass die Funktion an **jeder** Aufrufstelle auch benutzt wird.
Ein vergessenes Vorkommen laesst ``test_urls.py`` gruen.

Die Invariante ist bei allen Aufrufen dieselbe: der feste Teil des Pfades vor
dem Bezeichner muss stehen bleiben. Wer ihn verlaesst, erreicht einen anderen
Endpunkt -- mit den Zugangsdaten des Dienstes.
"""

import json

import httpx
import pytest

from edusharing import AsyncRepository
from edusharing.errors import EduSharingError

REPO = "https://repo.test/edu-sharing"

# Die Formen, die beim Audit nachweislich ausgebrochen sind, plus die
# Trennzeichen, die eine URL sonst noch zerlegen.
ANGRIFFE = [
    "../../../admin/v1/applications",
    "abc/../../../../etc",
    "abc?admin=1",
    "abc#frag",
    "abc/children",
    "a b",
]


def _node(node_id: str) -> dict:
    return {"node": {"ref": {"id": node_id}, "name": "n", "type": "ccm:io",
                     "access": ["Read"], "properties": {},
                     "content": {"hash": "-1"}}}


def _repo_mit_protokoll(antwort_id: str = "x") -> tuple[AsyncRepository, list[httpx.URL]]:
    """``antwort_id`` ist die ID, die der Server in ``ref.id`` zurueckmeldet.

    Das modelliert den realistischen Weg: die Bibliothek erhaelt eine ID aus
    Antwortdaten und baut damit den naechsten Pfad.
    """
    gesehen: list[httpx.URL] = []
    NODE = _node(antwort_id)

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(request.url)
        if request.method == "POST" and request.url.path.endswith("/children"):
            # Wie die Instanz: die Antwort des Anlegens traegt, was gespeichert
            # wurde. Eine feste Antwort loeste die Rueckleseprobe zu Recht aus.
            angelegt = dict(NODE["node"])
            angelegt["properties"] = json.loads(request.content)
            return httpx.Response(200, json={"node": angelegt})
        if "/values" in request.url.path:
            return httpx.Response(200, json={"values": []})
        if "queries" in request.url.path:
            return httpx.Response(200, json={"nodes": [], "pagination": {"total": 0}})
        if request.method == "DELETE" or "references" in request.url.path:
            return httpx.Response(200, content=b"")
        return httpx.Response(200, json=NODE)

    repo = AsyncRepository(
        REPO, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return repo, gesehen


def _pfade_bleiben_unter(gesehen: list[httpx.URL], praefix: str) -> None:
    """Geprueft wird ``raw_path``, nicht ``path``.

    httpx dekodiert in ``path`` die Prozentzeichen wieder: ein kodierter
    Schraegstrich sieht dort aus wie ein echter. Was der Server als Pfadsegment
    sieht, steht in ``raw_path`` -- und nur darauf kommt es an.
    """
    assert gesehen, "kein Request abgesetzt -- der Test prueft nichts"
    for url in gesehen:
        gesendet = url.raw_path.decode()
        assert gesendet.startswith(praefix), (
            f"Pfad verlaesst {praefix!r}: {gesendet!r}"
        )


@pytest.mark.parametrize("boese", ANGRIFFE)
async def test_node_id_bleibt_im_pfad(boese):
    repo, gesehen = _repo_mit_protokoll()
    async with repo:
        await repo.node(boese)
    _pfade_bleiben_unter(gesehen, "/edu-sharing/rest/node/v1/nodes/-home-/")


@pytest.mark.parametrize("boese", ANGRIFFE)
async def test_parent_id_beim_anlegen_bleibt_im_pfad(boese):
    repo, gesehen = _repo_mit_protokoll()
    async with repo:
        await repo.create_node(boese, name="x.txt")
    _pfade_bleiben_unter(gesehen, "/edu-sharing/rest/node/v1/nodes/-home-/")


@pytest.mark.parametrize("boese", ANGRIFFE)
async def test_schreibwege_bleiben_im_pfad(boese):
    """update, set_property, delete und die Dateiwege."""
    repo, gesehen = _repo_mit_protokoll(antwort_id=boese)
    async with repo:
        node = await repo.nodes.get("harmlos")
        assert node.id == boese, "Vorbedingung: der Node traegt die boese ID"
        await node.set_property("ccm:x", "1", verify=False)
        await node.delete()
        await node.content.text()
    _pfade_bleiben_unter(gesehen, "/edu-sharing/rest/node/v1/nodes/-home-/")


@pytest.mark.parametrize("boese", ANGRIFFE)
async def test_sammlungs_ids_bleiben_im_pfad(boese):
    repo, gesehen = _repo_mit_protokoll()
    async with repo:
        await repo.add_to_collection(boese, boese)
        await repo.remove_from_collection(boese, boese)
        await repo.create_collection("Titel", parent=boese)
    _pfade_bleiben_unter(gesehen, "/edu-sharing/rest/collection/v1/collections/-home-/")


@pytest.mark.parametrize("boese", ANGRIFFE)
async def test_metadatensatz_bleibt_im_pfad(boese):
    """Der Metadatensatz kommt aus der Konfiguration, nicht aus Fremddaten --
    aber er steht im selben Pfad und wird genauso behandelt."""
    repo = AsyncRepository(REPO, metadataset=boese, client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(
            200, json={"nodes": [], "pagination": {"total": 0}}))))
    gesehen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(request.url)
        if "/values" in request.url.path:
            return httpx.Response(200, json={"values": []})
        return httpx.Response(200, json={"nodes": [], "pagination": {"total": 0}})

    repo = AsyncRepository(REPO, metadataset=boese, client=httpx.AsyncClient(
        transport=httpx.MockTransport(handler)))
    async with repo:
        await repo.search("Physik")
        await repo.vocab.values("ccm:taxonid")
    for url in gesehen:
        gesendet = url.raw_path.decode()
        assert gesendet.startswith((
            "/edu-sharing/rest/search/v1/queries/-home-/",
            "/edu-sharing/rest/mds/v1/metadatasets/-home-/",
        )), f"Pfad verlaesst den festen Teil: {gesendet!r}"


# --- F07 (Fremdpruefung 09.09.2026): die beiden Punktsegmente --------------
#
# ``quote(value, safe="")`` kodiert alles, was Pfadgrenzen verschieben *kann*
# -- ausser den beiden Werten, die selbst welche sind. ``.`` und ``..`` gehen
# unveraendert durch und werden erst beim Bauen der URL normalisiert.
#
# Gemessen am 09.09.2026 mit kontrollierten DELETE-Anfragen:
#
#     ``.``   /node/v1/nodes/-home-/.   ->  /node/v1/nodes/-home-
#     ``..``  /node/v1/nodes/-home-/..  ->  /node/v1/nodes
#
# Der Praefix-Test oben faengt das nicht: der gekuerzte Pfad ist ein echter
# Praefix des erwarteten. Geprueft wird darum das Staerkere -- es geht gar
# keine Anfrage hinaus.

PUNKTSEGMENTE = [".", ".."]


@pytest.mark.parametrize("punkt", PUNKTSEGMENTE)
async def test_ein_punktsegment_erreicht_das_netz_nicht(punkt):
    repo, gesehen = _repo_mit_protokoll()
    async with repo:
        with pytest.raises(EduSharingError):
            await repo.node(punkt)
        with pytest.raises(EduSharingError):
            await repo.create_node(punkt, name="x.txt")
        with pytest.raises(EduSharingError):
            await repo.add_to_collection(punkt, "harmlos")
        with pytest.raises(EduSharingError):
            await repo.remove_from_collection("harmlos", punkt)
    assert gesehen == [], "keine dieser Anfragen darf hinausgehen"


async def test_die_wache_sieht_ueberhaupt_etwas():
    """Die Gegenprobe: eine gewoehnliche ID geht weiterhin hinaus.

    Ohne sie waere der Test darueber gruen, wenn ``repo.node`` immer wirft.
    """
    repo, gesehen = _repo_mit_protokoll()
    async with repo:
        await repo.node("harmlos-123")
    assert len(gesehen) == 1
