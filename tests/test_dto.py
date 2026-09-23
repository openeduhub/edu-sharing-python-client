"""Ein Knotensatz, einmal gelesen.

Derselbe Datensatz wurde an fuenf Stellen verschieden gelesen: ``_first``
dreimal definiert (einmal mit ``""`` statt ``None`` als Ergebnis), ``_bare``
zweimal, die Ansichts-URL an fuenf Stellen gebaut, ``(raw["ref"])["id"]`` an
zwoelf, ``pagination.total`` an acht. Wer ein Feld umbenennt, muss es dann in
einem Dutzend Dateien jagen (Audit MNT-1).

Hier steht, was die eine Lesart leistet -- und eine Wache, die eine neue
Kopie beim naechsten Mal auffallen laesst.
"""

import ast
from pathlib import Path

import pytest

from edusharing.dto import (
    bare_id,
    first,
    node_id_of,
    page_cut,
    page_total,
    render_url,
    stored_title_of,
    title_of,
)
from edusharing.nodes import Node
from edusharing.results import SearchHit
from edusharing.skills_registry import _title as registry_title

QUELLE = Path(__file__).resolve().parent.parent / "src" / "edusharing"


# --- first -----------------------------------------------------------------


@pytest.mark.parametrize(("wert", "erwartet"), [
    (["a", "b"], "a"),
    ([], None),
    ("a", "a"),
    ("", ""),
    (None, None),
    (0, "0"),
    (False, "False"),
    ([42], "42"),
    ([0], "0"),
    ([""], ""),
])
def test_first_nimmt_den_ersten_wert(wert, erwartet):
    """edu-sharing liefert Eigenschaften immer als Liste, auch einzelne.

    Eine Regel fuer beide Formen: **nur Abwesenheit und die leere Liste sind
    keine Werte.** ``[""]`` ergibt ``""``, und ein blankes ``0`` ergibt
    ``"0"``.

    Der blanke Fall galt bis zum 08.09.2026 als nicht gesetzt, mit einem
    eigenen Testfall (Audit COR-9). Ein gemessener Schaden stand nicht
    dahinter: jeder Aufruf von ``first`` liest ``properties.get(...)``, und
    edu-sharing schickt Listen -- der Skalarzweig ist ein Sicherheitsnetz,
    das in der Praxis nie ein blankes ``0`` trug.

    Falsch war, dass dieses Netz eine **andere** Regel hatte als die, die
    ``flows/serialize.py`` fuer dieselbe Frage aufschreibt: "``0`` und
    ``False`` sind Werte; nur Abwesenheit und die leere Liste sind es nicht."
    Ein Sicherheitsnetz, das der Regel widerspricht, die es absichert, hat
    die falsche Form fuer den Tag, an dem es doch etwas faengt. Jetzt gilt
    eine Regel an beiden Stellen.
    """
    assert first(wert) == erwartet


def test_first_gibt_none_und_nicht_leerstring():
    """Die Registry gab bisher ``""`` zurueck, die beiden anderen ``None``.
    Ein Aufrufer, der auf ``is None`` prueft, sah je nach Herkunft etwas
    anderes (Audit MNT-1)."""
    assert first([]) is None
    assert first(None) is None


# --- node_id_of ------------------------------------------------------------


def test_node_id_of_liest_die_referenz():
    assert node_id_of({"ref": {"id": "9f2c"}}) == "9f2c"


@pytest.mark.parametrize("roh", [{}, {"ref": None}, {"ref": {}}, {"ref": {"id": None}}])
def test_node_id_of_ist_leer_wenn_es_keine_gibt(roh):
    """Nie ``None``: der Wert geht in URLs und Routen, und ein ``None`` dort
    faellt erst weit weg auf."""
    assert node_id_of(roh) == ""


# --- bare_id ---------------------------------------------------------------


@pytest.mark.parametrize(("ref", "erwartet"), [
    ("workspace://SpacesStore/9f2c", "9f2c"),
    ("9f2c", "9f2c"),
    ("", ""),
])
def test_bare_id_streift_das_praefix_ab(ref, erwartet):
    """Der Seitenbauer schreibt volle Store-Referenzen; jede REST-Route dieser
    Bibliothek nimmt die blanke id."""
    assert bare_id(ref) == erwartet


# --- render_url ------------------------------------------------------------


def test_render_url_baut_die_ansichts_adresse():
    assert render_url("https://repo.test/edu-sharing", "9f2c") == (
        "https://repo.test/edu-sharing/components/render/9f2c")


def test_render_url_ohne_id_ist_leer():
    """Eine Adresse auf nichts ist keine Adresse -- fuenf Baustellen, drei
    Antworten darauf (Audit MNT-1)."""
    assert render_url("https://repo.test/edu-sharing", "") == ""


# --- page_total ------------------------------------------------------------


def test_page_total_liest_die_gesamtzahl():
    assert page_total({"pagination": {"total": 128, "from": 0}}) == 128


@pytest.mark.parametrize("antwort", [{}, {"pagination": None}, {"pagination": {}},
                                     {"pagination": {"total": None}}])
def test_page_total_faellt_auf_die_vorgabe(antwort):
    """Traegt eine Antwort keine Gesamtzahl, sagt der Aufrufer, was gilt.

    Dass es solche Antworten gibt, ist eine **Vorsorge und keine
    Beobachtung**: die Behauptung, ``ngsearch`` antworte mit
    ``pagination: null``, stand bis zum 09.09.2026 im Docstring und ist
    gemessen falsch -- die Suche nennt ``total: 1591`` fuer ein Wort mit
    1591 Datensaetzen und ``total: 0`` fuer eines ohne.
    """
    assert page_total(antwort) == 0
    assert page_total(antwort, default=7) == 7


# --- page_cut --------------------------------------------------------------
#
# Gefragt wird mit ``maxItems=limit + 1``; ``limit`` ist, was der Aufrufer
# seinem eigenen Leser zusagt. Beide Endpunkte beachten ``maxItems`` genau --
# gemessen am 09.09.2026 gegen edu-sharing 11.0.


def test_page_cut_sieht_den_einen_datensatz_ueber_dem_limit():
    """Der Kern: die Seite beantwortet die Frage selbst."""
    assert page_cut(list(range(6)), {}, 5) is True


def test_page_cut_ohne_gesamtzahl_und_genau_am_limit_ist_vollstaendig():
    """Und das ist die Haelfte, die vorher fehlte: genau ``limit`` Datensaetze
    sind vollstaendig, weil einer mehr angefordert war und nicht kam."""
    assert page_cut(list(range(5)), {}, 5) is False


@pytest.mark.parametrize("antwort", [{}, {"pagination": None},
                                     {"pagination": {"total": None}},
                                     {"pagination": {"total": ""}}])
def test_page_cut_verlaesst_sich_nicht_auf_eine_genannte_zahl(antwort):
    """Alle Formen von "nichts gesagt". Ohne den zusaetzlichen Datensatz war
    die Antwort hier genau dann ``False``, wenn niemand etwas sagte -- also
    dort, wo sie am wenigsten wert war."""
    assert page_cut(list(range(6)), antwort, 5) is True
    assert page_cut(list(range(5)), antwort, 5) is False


def test_page_cut_glaubt_einer_gesamtzahl_ueber_dem_limit():
    """Wer 250 sagt und 6 liefert, hat die Frage selbst beantwortet -- da
    braucht es den zusaetzlichen Datensatz nicht."""
    assert page_cut(list(range(3)), {"pagination": {"total": 250}}, 5) is True


def test_page_cut_faellt_nicht_auf_eine_gemeldete_seitengroesse_herein():
    """Ein Server, der als ``total`` die **Seitengroesse** nennt, ist von einem
    ehrlichen nicht zu unterscheiden. Die Datensaetze entscheiden trotzdem."""
    assert page_cut(list(range(6)), {"pagination": {"total": 6}}, 5) is True


def test_page_cut_vergleicht_die_zahl_mit_dem_gezeigten_nicht_mit_dem_limit():
    """Ein Server, der 9 nennt und 3 liefert, hat die Frage beantwortet --
    auch wenn beide Zahlen unter dem Deckel liegen.

    Gegen ``limit`` verglichen fiel genau das durch (Pruefung 09.09.2026).
    Dass die zwei Zahlen vergleichbar sind, ist gemessen: ``pagination.total``
    beachtet ``filter`` -- ein Ordner mit drei Dateien und zwei Unterordnern
    antwortet auf ``filter=files`` mit ``total: 3``, nicht 5.
    """
    assert page_cut([1, 2, 3], {"pagination": {"total": 9}}, 50) is True
    assert page_cut([1, 2, 3], {"pagination": {"total": 3}}, 50) is False


def test_page_cut_glaubt_den_datensaetzen_gegen_eine_zu_kleine_zahl():
    """Ein Server, der 51 Datensaetze schickt und ``total: 40`` nennt,
    widerspricht sich. Was angekommen **ist**, wiegt schwerer als was
    behauptet wird -- sonst haengt die Antwort wieder an einer Zusage.

    Genau in dieser Form unterscheidet sich der Helfer von der oertlichen
    Bedingung, die ``skills_registry`` vorher trug (erschoepfend verglichen
    am 09.09.2026: 51 von 6812 Kombinationen, alle diese).
    """
    assert page_cut(list(range(51)), {"pagination": {"total": 40}}, 50) is True


def test_page_cut_nimmt_eine_genannte_null_als_antwort():
    """Eine genannte ``0`` ist eine Auskunft, kein Schweigen -- und eine leere
    Sammlung ist nicht gekuerzt."""
    assert page_cut([], {"pagination": {"total": 0}}, 5) is False

# --- Die Wache -------------------------------------------------------------


#: Die vier Antwortformen, in denen eine Gesamtzahl vorkommen kann oder auch
#: nicht. ``geliefert`` ist, was der Server auf ``maxItems=limit + 1`` schickt.
def _seitenantwort(bestand: int, geliefert: int, form: str) -> dict:
    if form == "ehrlich":
        return {"pagination": {"total": bestand, "from": 0, "count": geliefert}}
    if form == "schweigt":
        return {}
    if form == "null":
        return {"pagination": None}
    if form == "seitengroesse":
        return {"pagination": {"total": geliefert, "from": 0, "count": geliefert}}
    raise AssertionError(form)


@pytest.mark.parametrize("form", ["ehrlich", "schweigt", "null", "seitengroesse"])
def test_page_cut_ist_wahr_genau_wenn_es_mehr_gibt(form):
    """Die Eigenschaft, auf die sieben Aufrufer bauen -- ueber alle Bestaende.

    Beantwortet ein Server ``maxItems=limit + 1`` mit ``min(bestand, limit+1)``
    Datensaetzen -- gemessen tun das beide Auflistungsendpunkte --, dann muss
    gelten: ``page_cut`` ist wahr **genau dann**, wenn es mehr als ``limit``
    gibt. Unabhaengig davon, ob und wie der Server eine Gesamtzahl nennt.

    Die Einzeltests darueber sagen, *warum* jede Form vorkommt; dieser sagt,
    dass keine von ihnen die Antwort verschiebt.

    **Was er nicht zeigt**, und das ist gemessen: unter einem Server, der
    ``maxItems`` beachtet, ist die Datensatz-Haelfte allein schon
    hinreichend -- die Mutationsprobe am 09.09.2026 liess "nur die
    Datensaetze" und "gegen ``limit`` statt gegen das Gezeigte" hier gruen
    durch. Die genannte Gesamtzahl verdient ihren Platz gegen Server, die
    sich widersprechen, und dafuer stehen die Einzeltests darueber. Eine
    Eigenschaft ist so stark wie ihre Annahme.
    """
    limit = 50
    for bestand in range(3 * limit):
        geliefert = min(bestand, limit + 1)
        ist = page_cut(list(range(geliefert)),
                       _seitenantwort(bestand, geliefert, form), limit)
        assert ist is (bestand > limit), (form, bestand, geliefert, ist)


def _definierte(name: str) -> list[str]:
    """Jede Datei, die eine Funktion dieses Namens selbst definiert."""
    gefunden = []
    for pfad in sorted(QUELLE.rglob("*.py")):
        if "_generated" in pfad.parts or pfad.name == "dto.py":
            continue
        baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
                gefunden.append(pfad.relative_to(QUELLE).as_posix())
    return gefunden


@pytest.mark.parametrize("name", ["_first", "_bare", "first", "bare_id", "node_id_of"])
def test_niemand_definiert_die_leser_ein_zweites_mal(name):
    """Die Doppelung entstand nicht auf einmal, sondern eine Kopie nach der
    anderen. Diese Wache faellt beim naechsten Mal auf, statt beim naechsten
    Audit."""
    assert _definierte(name) == []


# --- title_of --------------------------------------------------------------


@pytest.mark.parametrize(("roh", "erwartet"), [
    ({"title": "Angezeigt", "properties": {"cclom:title": ["LOM"],
                                           "cm:title": ["Alfresco"],
                                           "cm:name": ["datei.pdf"]}}, "Angezeigt"),
    ({"properties": {"cclom:title": ["LOM"], "cm:title": ["Alfresco"],
                     "cm:name": ["datei.pdf"]}}, "LOM"),
    ({"properties": {"cm:title": ["Alfresco"], "cm:name": ["datei.pdf"]}}, "Alfresco"),
    ({"properties": {"cm:name": ["datei.pdf"]}}, "datei.pdf"),
    ({"properties": {}}, ""),
    ({}, ""),
    ({"title": "", "properties": {"cm:name": ["datei.pdf"]}}, "datei.pdf"),
])
def test_title_of_folgt_einer_kette(roh, erwartet):
    """Was die Schnittstelle selbst anzeigt, dann der LOM-Titel, dann der von
    Alfresco, zuletzt der Dateiname. Ein Name ist besser als nichts, und die
    ausdruecklichen Titel stehen vor ihm."""
    assert title_of(roh) == erwartet


def test_alle_objekte_lesen_denselben_titel():
    """Der Kern des Befunds: derselbe Datensatz zeigte je nach Objekt einen
    anderen Titel. Ein Datensatz mit LOM-Titel und abweichendem Dateinamen kam
    als Treffer als 'arbeitsblatt.pdf' an, als Knoten als 'Bruchrechnung'
    (Audit MNT-1)."""
    roh = {"ref": {"id": "n1"},
           "properties": {"cclom:title": ["Bruchrechnung"],
                          "cm:name": ["arbeitsblatt.pdf"]}}
    assert Node(roh, None).title == "Bruchrechnung"
    assert SearchHit.from_node(roh, "https://repo.test").title == "Bruchrechnung"
    assert registry_title(roh) == "Bruchrechnung"


@pytest.mark.parametrize(("roh", "erwartet"), [
    ({"title": "Angezeigt", "properties": {"cm:name": ["datei.pdf"]}}, "Angezeigt"),
    ({"properties": {"cclom:title": ["LOM"], "cm:name": ["datei.pdf"]}}, "LOM"),
    ({"properties": {"cm:title": ["Alfresco"], "cm:name": ["datei.pdf"]}}, "Alfresco"),
    ({"properties": {"cm:name": ["datei.pdf"]}}, ""),
    ({}, ""),
])
def test_stored_title_of_faellt_nicht_auf_den_namen_zurueck(roh, erwartet):
    """Das Gegenstueck zu ``title_of``: was ein Schreibvorgang erhaelt.

    Der Anzeigetitel faellt auf den Dateinamen zurueck. Diesen beim Erhalten
    eines Titels zu schreiben, legt Metadaten an, die niemand verlangt hat --
    gemessen an einer Sammlung ohne Titel, deren Beschreibung geaendert wurde
    (Review 08.09.2026)."""
    assert stored_title_of(roh) == erwartet


def test_die_beiden_titelfragen_unterscheiden_sich_genau_dort():
    roh = {"properties": {"cm:name": ["arbeitsblatt.pdf"]}}
    assert title_of(roh) == "arbeitsblatt.pdf"
    assert stored_title_of(roh) == ""


@pytest.mark.parametrize("wert", [None, ""])
def test_page_total_nimmt_die_vorgabe_wenn_nichts_gesagt_ist(wert):
    """``None`` und ``""`` heissen beide "nicht gesagt". Ein leeres Feld darf
    die Auflistung nicht mit einem ValueError beenden."""
    assert page_total({"pagination": {"total": wert}}, default=7) == 7


def test_eine_genannte_null_ist_eine_antwort():
    """Der Befund, um den es ging: acht Aufrufstellen schrieben ``or``, und
    ein Aufrufer mit einer Vorgabe ungleich 0 bekam sie bei einer leeren
    Auflistung zurueck (Review 08.09.2026)."""
    assert page_total({"pagination": {"total": 0}}, default=7) == 0
