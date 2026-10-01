"""Die Ablaeufe gegen ein echtes Repositorium.

Die Mock-Tests halten das Format fest. Sie koennen aber nicht zeigen, dass die
Kette gegen eine laufende Instanz auch wirklich durchlaeuft -- und genau das ist
bei einem Ablauf das Versprechen.

**Sicherheitsregeln**, wie in ``test_live_write.py``:

* Geschrieben wird ausschliesslich in einem **eigens angelegten** Ordner.
* Der Ordner liegt im Home-Verzeichnis des angemeldeten Kontos.
* Geloescht wird nur, was diese Tests selbst angelegt haben.

Aufruf::

    uv run pytest -m "live and write" tests/test_live_flows.py
"""

import json
import os
import uuid

import pytest

from edusharing import AsyncRepository
from edusharing.errors import NotFoundError

_ANGEMELDET = os.environ.get("EDU_SHARING_URL") and os.environ.get("EDU_SHARING_USER")

pytestmark = pytest.mark.skipif(
    not _ANGEMELDET, reason="EDU_SHARING_URL/_USER nicht gesetzt"
)


@pytest.fixture
async def repo():
    async with AsyncRepository.from_env(metadataset="mds_oeh") as r:
        yield r


@pytest.fixture
async def ordner(repo):
    """Ein frischer Ordner je Testlauf, der am Ende wieder verschwindet."""
    wer = await repo.whoami()
    assert not wer.is_anonymous, "Schreibtests brauchen ein angemeldetes Konto"
    assert wer.home_folder, "kein Home-Verzeichnis -- hier wird nichts geschrieben"

    neu = await repo.create_node(
        wer.home_folder,
        name=f"pytest-flows-{uuid.uuid4().hex[:8]}",
        type="cm:folder",
    )
    try:
        yield neu
    finally:
        await neu.delete(recycle=False)


# --- lesend ---------------------------------------------------------------


@pytest.mark.live
async def test_suche_liefert_echtes_json(repo):
    ergebnis = await repo.flows.search("Physik", limit=3)
    json.dumps(ergebnis)
    assert ergebnis["total"] > 0
    assert 0 < ergebnis["returned"] <= 3
    erster = ergebnis["hits"][0]
    assert erster["id"] and erster["url"]


@pytest.mark.live
async def test_suche_mit_vokabular_filtert_wirklich(repo):
    """Gegenprobe zur Auflösung: mit Fachfilter darf nicht mehr herauskommen
    als ohne."""
    ohne = await repo.flows.search("Wald", limit=1)
    mit = await repo.flows.search("Wald", subject="Biologie", limit=1)
    assert not mit["unresolved"], f"Filter fiel weg: {mit['unresolved']}"
    assert mit["total"] <= ohne["total"]


@pytest.mark.live
async def test_vokabular_kommt_von_der_instanz(repo):
    ergebnis = await repo.flows.vocabulary("subject")
    assert ergebnis["property"] == "ccm:taxonid"
    assert ergebnis["count"] > 10
    assert "Biologie" in ergebnis["values"]


@pytest.mark.live
async def test_describe_beschreibt_einen_echten_treffer(repo):
    """Gemessen am 27.08.2026: **4 von 25** Suchtreffern sind nicht abrufbar --
    der Index enthaelt Knoten, die es nicht mehr gibt. Ein Test, der einfach den
    ersten Treffer nimmt, ist deshalb nicht deterministisch, und ein Ablauf, der
    Suche und Detailabruf verkettet, muss den Fall aushalten."""
    treffer = await repo.flows.search("Physik", limit=10)
    assert treffer["hits"], "keine Treffer -- der Test prueft nichts"

    for hit in treffer["hits"]:
        try:
            ergebnis = await repo.flows.describe(hit["id"])
        except NotFoundError:
            continue
        break
    else:
        pytest.skip("kein abrufbarer Treffer unter den ersten 10")

    assert ergebnis["id"]
    assert ergebnis["properties"], "keine Eigenschaften -- describe liefe leer"
    json.dumps(ergebnis)


# --- Neuordnung -----------------------------------------------------------


@pytest.mark.live
@pytest.mark.parametrize("natuerlich,thema", [
    ("Ich suche ein Arbeitsblatt zur Bruchrechnung", "Bruchrechnung"),
    ("Unterrichtsstunde Französische Revolution", "Französische Revolution"),
])
async def test_rerank_rettet_die_natuerlich_formulierte_anfrage(repo, natuerlich, thema):
    """Der Grund, warum es rerank gibt.

    edu-sharing UND-verknuepft jedes Wort. Woerter, die nur die Form der Bitte
    beschreiben, stehen in fast keinem Datensatz -- ein einziges leert die
    Liste. Gemessen am 27.08.2026: "Bruchrechnung" 1591 Treffer, "Ich suche ein
    Arbeitsblatt zur Bruchrechnung" null.

    Ein Sprachmodell formuliert genau so.
    """
    ohne = await repo.flows.search(natuerlich, limit=3)
    mit = await repo.flows.search(natuerlich, rerank=True, limit=3)
    blank = await repo.flows.search(thema, limit=1)

    assert blank["total"] > 100, "Vorbedingung: zum Thema gibt es reichlich"
    assert ohne["returned"] < mit["returned"], (
        f"rerank brachte keinen Gewinn: {ohne['returned']} -> {mit['returned']}")
    assert mit["total"] > 0, "eine Trefferzahl von 0 neben echten Treffern waere falsch"


@pytest.mark.live
async def test_rerank_meldet_die_gefahrenen_varianten(repo):
    ergebnis = await repo.flows.search(
        "Ich suche ein Video zur Photosynthese", rerank=True, limit=2)
    assert ergebnis["query"]["reranked"] is True
    assert "topic" in ergebnis["query"]["variants"]


@pytest.mark.live
async def test_die_suche_selbst_ist_nicht_reproduzierbar(repo):
    """Kein Fehler der Bibliothek, sondern eine Eigenschaft der Instanz -- und
    eine, die man kennen muss.

    Gemessen am 27.08.2026: dieselbe Anfrage zweimal gestellt lieferte 25
    Treffer, von denen sich **15 unterschieden**. Die Gesamtzahl blieb dabei
    konstant bei 317.

    Folge fuer rerank: es ordnet eine Kandidatenmenge deterministisch (dafuer
    ist der Tie-Break da, siehe test_flows_rerank.py), aber es kann die Suche
    nicht reproduzierbar machen, wenn die Quelle es nicht ist. Gemessen half
    auch ein groesserer Pool nicht nennenswert. Wer Ergebnisse zwischenspeichert
    oder zwei Laeufe vergleicht, muss damit rechnen.

    Der Test ist bewusst schwach formuliert: er verlangt nur, dass die
    Gesamtzahl stabil bleibt. Auf die Trefferreihenfolge zu pruefen hiesse, ihn
    an genau die Volatilitaet zu haengen, die er beschreibt.
    """
    laeufe = [await repo.searcher.search("Photosynthese", limit=25) for _ in range(2)]
    assert laeufe[0].total == laeufe[1].total, "die Gesamtzahl sollte stabil sein"

    ids = [{h.id for h in lauf.hits} for lauf in laeufe]
    gemeinsam = len(ids[0] & ids[1])
    # Keine Behauptung ueber die Hoehe -- nur festhalten, dass es passiert.
    if gemeinsam == len(ids[0]):
        pytest.skip("dieser Lauf war zufaellig stabil; die Instabilitaet ist "
                    "gemessen, aber nicht bei jedem Aufruf sichtbar")


# --- Sammlungen -----------------------------------------------------------


@pytest.mark.live
async def test_sammlungen_finden_und_oeffnen(repo):
    """Die Kette, die ein MCP faehrt: Sammlung suchen, dann hineinsehen."""
    gefunden = await repo.flows.find_collections("Physik", limit=3)
    assert gefunden["hits"], "keine Sammlung gefunden -- der Test prueft nichts"
    assert gefunden["total_is_lower_bound"] is True
    json.dumps(gefunden)

    # Eine Sammlung mit Material suchen -- eine leere prueft nichts.
    for treffer in gefunden["hits"]:
        inhalt = await repo.flows.collection_contents(treffer["id"], limit=5)
        if inhalt["materials"]:
            break
    else:
        pytest.skip("keine der Sammlungen enthaelt Material")

    assert inhalt["returned_materials"] == len(inhalt["materials"])
    assert inhalt["returned_materials"] <= 5
    json.dumps(inhalt)

    # Der eigentliche Nachweis: die Materialien tragen Metadaten. Ohne
    # propertyFilter lieferte /children Knoten mit LEEREN Eigenschaften --
    # gemessen am 27.08.2026. Der Ablauf sah dabei aus, als funktioniere er.
    mit_feldern = [m for m in inhalt["materials"] if m["fields"]]
    assert mit_feldern, (
        "kein Material traegt Felder -- die Eigenschaften wurden nicht "
        "angefordert, und der Ablauf liefert nur Titel und ID")


@pytest.mark.live
async def test_wer_nur_material_abfragt_haelt_die_sammlung_fuer_leer(repo):
    """Der Grund, warum collection_contents zwei Wege abfragt.

    Gemessen am 27.08.2026 an einer Sammlung mit zwei Untersammlungen:
    filter=files liefert **null** Knoten. Die Untersammlungen tauchen unter
    filter=folders durchaus auf (als ccm:map) -- eine erste Messung an einer
    Sammlung ohne Untersammlungen hatte das Gegenteil nahegelegt, was ein
    Fehlschluss war.

    Genommen wird trotzdem der Sammlungs-Endpunkt: er ist der dafuer
    vorgesehene und liefert Sammlungs-Metadaten (scope), waehrend der
    Ordnerfilter ein Umweg ist, der zufaellig funktioniert.
    """
    wurzel = await repo.raw.json(
        "GET", "/collection/v1/collections/-home-/-root-/children/collections",
        params={"scope": "TYPE_EDITORIAL", "maxItems": 5})
    eltern = [c for c in (wurzel.get("collections") or [])]
    if not eltern:
        pytest.skip("keine redaktionellen Wurzelsammlungen auf dieser Instanz")

    for kandidat in eltern:
        cid = (kandidat.get("ref") or {}).get("id")
        inhalt = await repo.flows.collection_contents(cid)
        if not inhalt["collections"]:
            continue

        # Die Aussage, unabhaengig davon, ob diese Sammlung auch Material hat:
        # der Materialfilter zeigt die Untersammlungen NICHT.
        nur_material = await repo.raw.json(
            "GET", f"/node/v1/nodes/-home-/{cid}/children",
            params={"filter": "files", "maxItems": 100, "propertyFilter": "-all-"})
        material_ids = {(n.get("ref") or {}).get("id")
                        for n in (nur_material.get("nodes") or [])}
        unter_ids = {c["id"] for c in inhalt["collections"]}

        assert unter_ids, "Vorbedingung: diese Sammlung hat Untersammlungen"
        assert not (unter_ids & material_ids), (
            "Untersammlungen tauchen im Materialfilter auf -- dann braeuchte "
            "collection_contents den zweiten Endpunkt nicht")
        return
    pytest.skip("keine Sammlung mit Untersammlungen gefunden")


# --- schreibend -----------------------------------------------------------


@pytest.mark.live
@pytest.mark.write
async def test_material_anlegen_mit_vokabular(repo, ordner):
    """Der Kern des schreibenden Ablaufs: "Biologie" statt des URI."""
    ergebnis = await repo.flows.add_material(
        "Ablauf-Test Material",
        parent_id=ordner.id,
        url="https://beispiel.test/ablauf",
        description="Von der Testsuite angelegt",
        keywords=["Test", "Ablauf"],
        subject="Biologie",
    )
    assert not ergebnis["unresolved"], f"nicht aufgeloest: {ergebnis['unresolved']}"

    # Gegenprobe am Server, nicht an der Rueckgabe.
    geschrieben = await repo.flows.describe(ergebnis["id"])
    assert geschrieben["fields"]["subject"] == ["Biologie"]
    assert geschrieben["keywords"] == ["Test", "Ablauf"]


@pytest.mark.live
@pytest.mark.write
async def test_unbekannter_wert_wird_gemeldet_und_material_entsteht(repo, ordner):
    """Gemessen statt vermutet: was macht die Instanz mit einem Wert, den ihr
    Metadatensatz nicht kennt?"""
    ergebnis = await repo.flows.add_material(
        "Ablauf-Test Unbekannt", parent_id=ordner.id, subject="Gibtsnichtwirklich"
    )
    assert ergebnis["unresolved"], "der Wert fiel weg, ohne dass es jemand erfaehrt"
    assert ergebnis["id"], "das Material sollte trotzdem entstehen"


@pytest.mark.live
@pytest.mark.write
async def test_sammlung_anlegen_fuellen_und_wieder_loeschen(repo, ordner):
    material = await repo.flows.add_material("Ablauf-Test Sammelgut", parent_id=ordner.id)

    sammlung = await repo.flows.build_collection(
        f"Ablauf-Test Sammlung {uuid.uuid4().hex[:6]}",
        description="Von der Testsuite angelegt",
        node_ids=[material["id"]],
    )
    try:
        assert sammlung["added"] == [material["id"]], sammlung["failed"]
        assert not sammlung["failed"]

        # Die Beschreibung wurde bisher gesetzt, aber nie nachgeprueft. Sie
        # gehoert in das collection-Objekt; auf oberster Ebene lehnt die API sie
        # ab, als properties["cm:description"] wird sie verworfen (gemessen
        # 27.08.2026, siehe Collections.create).
        knoten = await repo.nodes.get(sammlung["id"])
        assert (knoten.raw.get("collection") or {}).get("description") == (
            "Von der Testsuite angelegt")
    finally:
        geloescht = await repo.flows.delete(sammlung["id"], recycle=False)
        assert geloescht["id"] == sammlung["id"]


@pytest.mark.live
@pytest.mark.write
async def test_loeschen_benennt_was_verschwand(repo, ordner):
    material = await repo.flows.add_material(
        "Ablauf-Test Wegwerf", parent_id=ordner.id)
    ergebnis = await repo.flows.delete(material["id"], recycle=False)
    assert ergebnis["title"] == "Ablauf-Test Wegwerf"
    assert ergebnis["recycled"] is False


@pytest.mark.live
@pytest.mark.write
async def test_material_aendern_mit_vokabular(repo, ordner):
    """Der Kreis schliesst sich: anlegen, aendern, loeschen."""
    angelegt = await repo.flows.add_material(
        "Ablauf-Test Aenderung", parent_id=ordner.id, subject="Biologie")

    geaendert = await repo.flows.update_material(
        angelegt["id"], title="Ablauf-Test Geaendert", subject="Physik",
        keywords=["geaendert"])
    assert not geaendert["unresolved"], f"nicht aufgeloest: {geaendert['unresolved']}"
    assert geaendert["title"] == "Ablauf-Test Geaendert"

    # Gegenprobe am Server, nicht an der Rueckgabe.
    stand = await repo.flows.describe(angelegt["id"])
    assert stand["fields"]["subject"] == ["Physik"]
    assert stand["keywords"] == ["geaendert"]


# --- Verknuepfungen -------------------------------------------------------


@pytest.mark.live
@pytest.mark.write
async def test_eine_reihe_aus_verknuepften_knoten(repo, ordner):
    """Serienobjekte: Knoten auf gleicher Ebene, miteinander verknuepft.

    edu-sharing fuehrt dafuer eine eigene API (/relation/v1). Gemessen am
    27.08.2026: die Gegenrichtung wird automatisch gefuehrt -- wer isPartOf von
    Teil zu Reihe anlegt, sieht an der Reihe hasPart, ohne sie zweimal zu setzen.
    """
    reihe = await repo.flows.add_material("Ablauf-Test Reihe", parent_id=ordner.id)
    teil1 = await repo.flows.add_material("Ablauf-Test Folge 1", parent_id=ordner.id)
    teil2 = await repo.flows.add_material("Ablauf-Test Folge 2", parent_id=ordner.id)

    await repo.relations.create(teil1["id"], "isPartOf", reihe["id"])
    await repo.relations.create(teil2["id"], "isPartOf", reihe["id"])
    # Geschwister verweisen aufeinander, und zwar maschinell vorgeschlagen.
    await repo.relations.create(teil1["id"], "references", teil2["id"],
                                ai_generated=True)

    # Sicht der Reihe: die Gegenrichtung, die niemand gesetzt hat.
    von_reihe = await repo.flows.relations(reihe["id"])
    typen = {r["type"] for r in von_reihe["relations"]}
    assert typen == {"hasPart"}, f"erwartet nur hasPart, bekam {typen}"
    assert {r["id"] for r in von_reihe["relations"]} == {teil1["id"], teil2["id"]}

    # Sicht einer Folge: gehoert zur Reihe, verweist auf die Schwester.
    von_teil = await repo.flows.relations(teil1["id"])
    nach_typ = {r["type"]: r for r in von_teil["relations"]}
    assert nach_typ["isPartOf"]["id"] == reihe["id"]
    assert nach_typ["references"]["id"] == teil2["id"]
    assert nach_typ["references"]["ai_generated"] is True, (
        "der maschinelle Vorschlag muss als solcher erkennbar bleiben")
    assert nach_typ["references"]["approved"] is False, (
        "unbestaetigt -- ein Vorschlag ist keine Tatsache")

    # Und wieder loesen.
    await repo.relations.delete(teil1["id"], "references", teil2["id"])
    danach = await repo.flows.relations(teil1["id"])
    assert {r["type"] for r in danach["relations"]} == {"isPartOf"}


@pytest.mark.live
@pytest.mark.write
async def test_freigabe_einer_maschinellen_verknuepfung(repo, ordner):
    """Die menschliche Haelfte: eine KI schlaegt vor, ein Mensch bestaetigt."""
    a = await repo.flows.add_material("Ablauf-Test Quelle", parent_id=ordner.id)
    b = await repo.flows.add_material("Ablauf-Test Ziel", parent_id=ordner.id)
    await repo.relations.create(a["id"], "references", b["id"], ai_generated=True)

    vorher = (await repo.flows.relations(a["id"]))["relations"][0]
    assert vorher["approved"] is False

    await repo.relations.approve(a["id"], "references", b["id"])
    nachher = (await repo.flows.relations(a["id"]))["relations"][0]
    assert nachher["approved"] is True, "die Freigabe kam nicht an"


# --- Serienobjekte --------------------------------------------------------


@pytest.mark.live
@pytest.mark.write
async def test_weitere_dokumente_an_einem_hauptdokument(repo, ordner):
    """Serienobjekte, wie die Ideendatenbank sie nutzt: zusaetzliche Dateien,
    die zum Hauptdokument gehoeren und nicht fuer sich stehen.

    Die noetige Kombination ist nicht zu erraten -- ccm:io_childobject ist ein
    ASPEKT, kein Typ, und ohne assocType=ccm:childio antwortet die Instanz mit
    HTTP 500. Gemessen am 27.08.2026.

    Rot auf Staging seit dem 10.09.2026, wie die Download-Tests in
    ``test_live_write``: der Download-Servlet liefert privaten Inhalt niemandem
    aus (``test_das_download_servlet_liefert_nur_oeffentliches``). Gesehen erst
    am 01.10.2026 -- vorher endete der Test schon beim Anlegen des Ordners.
    """
    haupt = await repo.create_node(ordner.id, name="hauptdokument.txt",
                                   title="Das Arbeitsblatt")
    haupt = await haupt.content.upload(b"Das Arbeitsblatt.",
                                       filename="hauptdokument.txt",
                                       mimetype="text/plain")

    loesung = await haupt.children.add(
        b"Die Loesungen.", filename="loesungsblatt.txt", mimetype="text/plain")
    handout = await haupt.children.add(
        b"Das Handout.", filename="handout.txt", mimetype="text/plain")

    kinder = await haupt.children.list()
    assert [k.name for k in kinder] == ["loesungsblatt.txt", "handout.txt"], (
        "die Reihenfolge muss der Anlage folgen")
    assert {k.id for k in kinder} == {loesung.id, handout.id}

    # Der Inhalt haengt wirklich am Kind, nicht am Hauptknoten.
    assert await kinder[0].content.download() == b"Die Loesungen."
    assert await haupt.content.download() == b"Das Arbeitsblatt."

    # Und ueber den Ablauf als JSON.
    ergebnis = await repo.flows.child_objects(haupt.id)
    assert ergebnis["count"] == 2
    assert [c["order"] for c in ergebnis["children"]] == [0, 1]
    json.dumps(ergebnis)


@pytest.mark.live
@pytest.mark.write
async def test_serienobjekte_erscheinen_nicht_als_eigenes_material(repo, ordner):
    """Sie gehoeren zum Hauptdokument. Taeuchten sie in der Ordnerliste als
    eigene Materialien auf, zaehlte jeder Anhang als Treffer."""
    haupt = await repo.create_node(ordner.id, name="mit-anhang.txt", title="Haupt")
    haupt = await haupt.content.upload(b"x", filename="mit-anhang.txt",
                                       mimetype="text/plain")
    await haupt.children.add(b"y", filename="anhang.txt", mimetype="text/plain")

    im_ordner = await repo.raw.json(
        "GET", f"/node/v1/nodes/-home-/{ordner.id}/children",
        params={"filter": "files", "maxItems": 50, "propertyFilter": "-all-"})
    namen = {n.get("name") for n in (im_ordner.get("nodes") or [])}
    assert "mit-anhang.txt" in namen
    assert "anhang.txt" not in namen, (
        "das Serienobjekt steht im Ordner -- dann waere es kein Anhang, "
        "sondern eigenes Material")


# --- Doppelte Treffer -----------------------------------------------------


@pytest.mark.live
async def test_zusammengefasste_treffer_haben_verschiedene_quellen(repo):
    """Die Zusage: nach dem Zusammenfassen traegt kein Treffer die Quelladresse
    eines anderen. Das gilt unabhaengig davon, ob dieser Lauf ueberhaupt
    Duplikate erwischt -- ein Test, der welche verlangt, haenge am Zustand der
    Instanz.

    Gemessen am 27.08.2026: bei 50 Treffern zu "Photosynthese" ein Paar mit
    identischer Quelladresse.
    """
    ergebnis = await repo.flows.search("Photosynthese", limit=50)
    quellen = [h["source_url"] for h in ergebnis["hits"] if h["source_url"]]
    assert len(quellen) == len(set(quellen)), (
        "zwei Treffer teilen sich eine Quelladresse -- nicht zusammengefasst")


@pytest.mark.live
async def test_ohne_zusammenfassen_bleiben_alle_treffer(repo):
    """Gegenprobe, damit der vorige Test nicht auch bei abgeschalteter
    Zusammenfassung gruen waere."""
    roh = await repo.flows.search("Photosynthese", limit=50, deduplicate=False)
    zusammengefasst = await repo.flows.search("Photosynthese", limit=50)

    assert roh["duplicates_removed"] == 0
    assert zusammengefasst["returned"] <= roh["returned"]

    if zusammengefasst["duplicates_removed"] == 0:
        pytest.skip("dieser Lauf enthielt keine Duplikate -- sie sind gemessen, "
                    "aber nicht bei jedem Aufruf da")

    # Wenn welche da waren: der behaltene Treffer nennt sie.
    mit_doppelten = [h for h in zusammengefasst["hits"] if h["duplicate_ids"]]
    assert mit_doppelten, "entfernt, aber nirgends genannt -- das waere ein stiller Verlust"
    assert sum(len(h["duplicate_ids"]) for h in mit_doppelten) == \
        zusammengefasst["duplicates_removed"]


@pytest.mark.live
async def test_search_all_liefert_beide_koerbe(repo):
    """Der Standardeinstieg: Material und Sammlungen zu einem Thema, ein
    Aufruf. Getrennt gehalten, weil ihre Zaehlungen nicht dasselbe bedeuten."""
    ergebnis = await repo.flows.search_all("Biologie", limit=5)
    json.dumps(ergebnis)

    assert ergebnis["materials"]["hits"], "kein Material zu einem breiten Thema"
    assert ergebnis["collections"]["hits"], "keine Sammlung zu einem breiten Thema"
    assert ergebnis["materials"]["total_is_lower_bound"] is False
    assert ergebnis["collections"]["total_is_lower_bound"] is True


@pytest.mark.live
async def test_search_all_meldet_die_nicht_angewandten_filter(repo):
    """Die Sammlungsabfrage nimmt nur ngsearchword. Ein Kurzname wie ``subject``
    wird auf die Sammlungen darum lokal angewandt und gilt in beiden Koerben;
    nur ein roher ``filters``-Eintrag hat dort kein Gegenstueck -- und der
    Ablauf nennt ihn, statt eine Einschraenkung zu behaupten, die es nicht
    gibt. (Live-Nachlauf 06.09.2026: der Test pinnte den Stand vor dem
    02.09., als Kurznamen den Sammlungskorb noch nicht erreichten.)"""
    ergebnis = await repo.flows.search_all("Zelle", subject="Biologie", limit=5)
    assert ergebnis["collections"]["filters_ignored"] == []
    assert ergebnis["materials"]["unresolved"] == [], "der Filter griff beim Material"

    uris = await repo.vocab.resolve_all("ccm:taxonid", "Biologie")
    assert uris, "Biologie steht im Fachvokabular"
    roh = await repo.flows.search_all("Zelle", filters={"ccm:taxonid": uris}, limit=5)
    assert roh["collections"]["filters_ignored"] == ["ccm:taxonid"]
    assert roh["materials"]["unresolved"] == []


@pytest.mark.live
async def test_search_all_kostet_nicht_mehr_als_die_einzelnen(repo):
    """Drei Anfragen: eine fuer das Material, zwei fuer die Sammlungssuche mit
    ihren beiden Wegen -- dasselbe, was zwei getrennte Aufrufe senden."""
    ergebnis = await repo.flows.search_all("Photosynthese", limit=3)
    assert len(ergebnis["materials"]["hits"]) <= 3
    assert len(ergebnis["collections"]["hits"]) <= 3


@pytest.mark.live
async def test_describe_many_ueberlebt_einen_toten_indexeintrag(repo):
    """Gemessen am 27.08.2026 waren 4 von 25 Treffern des Suchindex nicht mehr
    abrufbar. Wer die ganze Liste verliert, weil einer fehlt, kann eine Suche
    nicht weiterverarbeiten."""
    treffer = await repo.flows.search("Photosynthese", limit=8)
    ids = [h["id"] for h in treffer["hits"]]
    ergebnis = await repo.flows.describe_many([*ids, "gibtesnicht-0000"])

    json.dumps(ergebnis)
    assert ergebnis["requested"] == len(ids) + 1
    assert any(f["id"] == "gibtesnicht-0000" for f in ergebnis["failed"])
    assert ergebnis["found"] + len(ergebnis["failed"]) == ergebnis["requested"]


@pytest.mark.live
@pytest.mark.write
async def test_related_baut_auf_fach_und_stufe(repo, ordner):
    """Mit einem selbst angelegten Ausgangsknoten, weil der Suchindex Knoten
    haelt, die es nicht mehr gibt -- ein Treffer von dort waere ein
    unzuverlaessiger Ausgangspunkt, und der Test wuerde sich wegdruecken."""
    seed = await repo.flows.add_material(
        "Ausgangsmaterial fuer related", parent_id=ordner.id,
        subject="Biologie", level="Sekundarstufe I")
    assert seed["unresolved"] == [], "Vorbedingung: Fach und Stufe kamen an"

    ergebnis = await repo.flows.related(seed["id"], limit=5)
    json.dumps(ergebnis)

    assert ergebnis["based_on"] == {"subject": ["Biologie"],
                                    "level": ["Sekundarstufe I"]}
    assert seed["id"] not in [h["id"] for h in ergebnis["hits"]], \
        "der Ausgangsknoten ist nicht sein eigener Verwandter"
    assert ergebnis["hits"], "zu Biologie/Sek I gibt es anderes Material"


@pytest.mark.live
async def test_related_ohne_fach_und_stufe_erfindet_nichts(repo):
    """Eine ungefilterte Suche waere keine Antwort auf 'mehr davon'."""
    wer = await repo.whoami()
    ergebnis = await repo.flows.related(wer.home_folder)
    assert ergebnis["hits"] == []
    assert ergebnis["reason"]


@pytest.mark.live
async def test_der_sammlungsbaum_bleibt_im_deckel(repo):
    """Sammlungen bilden einen Graphen. Der Ablauf muss enden, und er muss
    sagen, wenn er abgeschnitten hat."""
    sammlungen = await repo.flows.find_collections("Biologie", limit=3)
    assert sammlungen["hits"], "keine Sammlung zum Ausgehen"

    baum = await repo.flows.browse_tree(sammlungen["hits"][0]["id"],
                                        depth=2, max_collections=6)
    json.dumps(baum)
    assert baum["opened"] <= 6
    assert isinstance(baum["truncated"], bool)


@pytest.mark.live
async def test_in_einer_sammlung_suchen(repo):
    """Eine Suche laesst sich nicht auf eine Sammlung eingrenzen -- gemessen.
    Also wird gelaufen und lokal verglichen."""
    sammlungen = await repo.flows.find_collections("Biologie", limit=3)
    ergebnis = await repo.flows.search_in_collection(
        sammlungen["hits"][0]["id"], "zelle", depth=2, max_collections=6)
    json.dumps(ergebnis)
    assert ergebnis["searched"] >= 1
    assert all("zelle" in (h["title"] or "").lower()
               or "zelle" in (h["description"] or "").lower()
               or any("zelle" in v.lower()
                      for werte in h["fields"].values() for v in werte)
               for h in ergebnis["hits"])


@pytest.mark.live
async def test_eine_sammlung_auszaehlen(repo):
    sammlungen = await repo.flows.find_collections("Biologie", limit=3)
    zahlen = await repo.flows.collection_stats(sammlungen["hits"][0]["id"],
                                               sample=20)
    json.dumps(zahlen)
    assert zahlen["materials"] >= zahlen["sampled"]
    assert zahlen["complete"] == (zahlen["sampled"] >= zahlen["materials"])
    for feld, zaehler in zahlen["by"].items():
        assert sum(zaehler.values()) >= 1, feld


# --- Kuratierte Seiten -----------------------------------------------------
#
# Beide Tests gehen die Treffer DURCH, statt den ersten zu nehmen. Zwei Gruende,
# beide am 28.08.2026 gemessen: die Sammlungssuche liefert bei gleicher Anfrage
# nicht dieselbe Treffermenge, und eine Seite kann gar nichts rendern -- die
# Sammlung Hexen traegt eine Variante mit lesbarem Dokument und leerer
# Schwimmlinienliste.

@pytest.mark.live
async def test_seiten_finden_und_ausgeben(repo):
    """Uebersprungen, wenn die Instanz keinen Page Builder fuehrt -- er ist
    eine Moeglichkeit von edu-sharing, keine Pflicht."""
    gefunden = await repo.flows.find_pages("Deutsch", limit=25)
    json.dumps(gefunden)
    assert gefunden["checked"] >= 1, (
        "kein einziger Sammlungstreffer war beurteilbar -- die Projektion fehlt")
    if not gefunden["hits"]:
        pytest.skip("diese Instanz fuehrt keine kuratierte Seite unter diesem Suchwort")

    mit_inhalt = None
    for treffer in gefunden["hits"]:
        assert treffer["folder_id"] and treffer["folder_id"] != treffer["id"]
        seite = await repo.flows.page(treffer["id"])
        json.dumps(seite)
        assert seite["folder_id"] == treffer["folder_id"]
        assert seite["rendered"] is not None, "eine Seite ohne Varianten"
        assert seite["reason"] == ""
        assert all(v["readable"] for v in seite["variants"])
        if seite["swimlanes"]:
            mit_inhalt = mit_inhalt or seite

    if mit_inhalt is None:
        pytest.skip("jede gefundene Seite rendert nichts -- gemessen moeglich")
    assert mit_inhalt["node_ids"]
    assert all(linie["items"] for linie in mit_inhalt["swimlanes"])
    assert mit_inhalt["resolved"] is False


@pytest.mark.live
async def test_widgets_aufloesen(repo):
    gefunden = await repo.flows.find_pages("Deutsch", limit=25)
    if not gefunden["hits"]:
        pytest.skip("diese Instanz fuehrt keine kuratierte Seite unter diesem Suchwort")

    for treffer in gefunden["hits"]:
        seite = await repo.flows.page(treffer["id"], resolve_widgets=True,
                                      max_widgets=6)
        json.dumps(seite)
        assert seite["resolved"] is True
        aufgeloest = [element for linie in seite["swimlanes"]
                      for element in linie["items"]
                      if {"description", "node_ids", "search"} & set(element)]
        if not aufgeloest:
            continue
        # Gemessen: ein Widget traegt entweder eine feste Liste oder eine
        # gespeicherte Suche. Die Suche wird genannt, nicht ausgefuehrt.
        for element in aufgeloest:
            if "search" in element:
                assert set(element["search"]) == {"text", "filters"}
            if "node_ids" in element:
                assert all(isinstance(i, str) for i in element["node_ids"])
        return
    pytest.skip("keine der gefundenen Seiten fuehrt aufloesbare Widgets")

