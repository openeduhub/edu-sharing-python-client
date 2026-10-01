"""Schreibtests gegen ein echtes Repositorium.

Laufen nur mit ``pytest -m write`` und gesetzten Zugangsdaten::

    uv run pytest -m write

Zugangsdaten allein genuegen nicht: das Konto braucht die Toolpermission
``TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS``. Gemessen am 21.09.2026 gegen
staging: von 90 schreibmarkierten Tests kamen 9 durch und 81 nicht -- 72 enden
hier in der Ordner-Fixture an ``HTTP 403 DAOToolPermissionException``, die
uebrigen 9 sind die schreibenden Beispiele. Material und Sammlungen darf
dasselbe Konto anlegen, Ordner nicht; die neun Gruenen sind genau die, die sich
eine Wegwerf-Sammlung bauen. Der Wegwerf-Ordner ist die Grenze, hinter der
diese Tests arbeiten.

**Sicherheitsregeln dieser Datei**, weil ein Schreibtest im falschen Ordner
fremde Bestaende beschaedigt:

* Es wird ausschliesslich in einem **eigens angelegten** Ordner gearbeitet.
* Der Ordner liegt im Home-Verzeichnis des angemeldeten Kontos; die Fixture
  prueft das, bevor sie irgendetwas schreibt.
* Geloescht wird nur, was diese Tests selbst angelegt haben.
* Kein Test fasst einen Knoten an, dessen ID er nicht selbst erzeugt hat.
"""

import asyncio
import json
import os
import uuid
import warnings

import pytest

from edusharing import AsyncRepository
from edusharing.errors import (
    EduSharingError,
    PermissionDeniedError,
    SilentDropError,
)
from edusharing.flows.duplicates import find_by_url
from edusharing.nodes import Node

pytestmark = [
    pytest.mark.write,
    pytest.mark.skipif(
        not (os.environ.get("EDU_SHARING_URL") and os.environ.get("EDU_SHARING_USER")),
        reason="EDU_SHARING_URL/_USER nicht gesetzt",
    ),
]

# Eine Property, die der Metadatensatz mds_oeh NICHT kennt -- geprueft gegen
# die Widget-Liste. Ueber sie laesst sich der stille Verlust ausloesen.
NICHT_IM_MDS = "ccm:oeh_collection_compendium_text"


@pytest.fixture
async def repo():
    async with AsyncRepository.from_env(metadataset="mds_oeh") as r:
        wer = await r.whoami()
        assert not wer.is_anonymous, "Schreibtests brauchen ein angemeldetes Konto"
        yield r


@pytest.fixture
async def ordner(repo):
    """Ein frischer Ordner je Testlauf, der am Ende wieder verschwindet."""
    wer = await repo.whoami()
    home = ((wer.raw.get("person") or {}).get("homeFolder") or {}).get("id")
    assert home, "kein Home-Verzeichnis -- ohne das wird hier nichts geschrieben"

    neu = await repo.create_node(
        home,
        name=f"pytest-edusharing-{uuid.uuid4().hex[:8]}",
        type="cm:folder",
    )
    assert neu.id, "Ordner nicht angelegt"
    try:
        yield neu
    finally:
        await _wegwerfen(neu)


@pytest.fixture
async def knoten(repo, ordner):
    """Ein Wegwerf-Knoten im Wegwerf-Ordner."""
    return await repo.create_node(
        ordner.id, name="material.txt", title="Ausgangstitel",
    )


# --- Anlegen ---------------------------------------------------------------

async def test_knoten_wird_angelegt(knoten):
    assert knoten.id
    assert knoten.url.endswith(knoten.id)


async def test_titel_landet_in_beiden_namensraeumen(knoten):
    """Die Oberflaeche rendert cm:title und cclom:title an verschiedenen
    Stellen -- nur eines zu setzen zeigt der Nutzerin etwas anderes an, als
    die Anwendung geschrieben hat."""
    assert knoten.get("cm:title") == "Ausgangstitel"
    assert knoten.get("cclom:title") == "Ausgangstitel"


# --- Der Kernfall: stiller Verlust ----------------------------------------

async def test_property_im_metadatensatz_wird_gespeichert(knoten):
    aktualisiert = await knoten.update(title="Geaendert")
    assert aktualisiert.get("cclom:title") == "Geaendert"


async def test_property_ausserhalb_des_metadatensatzes_wird_still_verworfen(knoten):
    """DER Grund fuer die Rueckleseprobe.

    edu-sharing antwortet auf diesen PUT mit **HTTP 200** und speichert
    nichts. Ohne die Probe meldete die Bibliothek hier Erfolg.
    """
    with pytest.raises(SilentDropError) as info:
        await knoten.update(properties={NICHT_IM_MDS: "Dieser Text geht verloren"})
    assert NICHT_IM_MDS in info.value.dropped


async def test_ohne_pruefung_bleibt_der_verlust_unbemerkt(knoten):
    """Die Gegenprobe: mit verify=False meldet derselbe Aufruf Erfolg -- und
    der Wert ist trotzdem weg. Das belegt, dass die Probe die Absicherung ist
    und nicht der Server."""
    await knoten.update(properties={NICHT_IM_MDS: "verloren"}, verify=False)
    frisch = await knoten._nodes.get(knoten.id)
    assert frisch.get(NICHT_IM_MDS) is None


async def test_direktweg_speichert_dieselbe_property(knoten):
    """set_property umgeht die Filterung des Metadatensatzes."""
    aktualisiert = await knoten.set_property(NICHT_IM_MDS, "Auf dem Direktweg")
    assert aktualisiert.get(NICHT_IM_MDS) == "Auf dem Direktweg"


async def test_direktweg_kann_loeschen(knoten):
    gesetzt = await knoten.set_property(NICHT_IM_MDS, "erst da")
    assert gesetzt.get(NICHT_IM_MDS) == "erst da"
    geleert = await gesetzt.set_property(NICHT_IM_MDS, None)
    assert geleert.get(NICHT_IM_MDS) is None


async def _wegwerfen(*knoten: Node) -> None:
    """Wegwerf-Objekte endgueltig loeschen -- alle, und ohne den Testfehler zu
    ueberschreiben.

    Drei Dinge, die dieser Helfer richtigstellt (Audit TST-3):

    ``recycle=False``. ``delete()`` legt in den Papierkorb, also hinterliess
    jeder Lauf dort einen ``pytest-edusharing-...``-Ordner, den jemand von
    Hand wegraeumen muss. Wegwerf-Objekte gehoeren nicht in den Papierkorb.

    Je Objekt gefangen. In ``eigene_seite`` lief das Aufraeumen als Schleife:
    scheiterte eine Loeschung, blieb der Rest liegen.

    Und gemeldet statt geworfen. Eine Ausnahme im ``finally`` ersetzt den
    Fehler, den der Test eigentlich gefunden hat -- man sieht dann das
    Aufraeumen scheitern und nicht mehr, woran es lag.
    """
    for eins in knoten:
        try:
            await eins.delete(recycle=False)
        except EduSharingError as exc:
            warnings.warn(
                f"Aufraeumen von {getattr(eins, 'id', eins)!r} fehlgeschlagen: {exc}",
                stacklevel=2,
            )


# --- Rechte und Loeschen ---------------------------------------------------

async def test_eigener_knoten_ist_beschreibbar(knoten):
    assert knoten.can_write is True


async def test_loeschen_entfernt_den_knoten(repo, ordner):
    eigener = await repo.create_node(ordner.id, name="wird-geloescht.txt")
    node_id = eigener.id
    await eigener.delete()
    from edusharing.errors import NotFoundError
    with pytest.raises(NotFoundError):
        await repo.node(node_id)


# --- Schlagworte: die geteilte Liste --------------------------------------

async def test_schlagworte_ergaenzen_ohne_fremde_zu_verlieren(repo, ordner):
    """Der Fall, der eine eigene Methode rechtfertigt: cclom:general_keyword
    pflegen mehrere Beteiligte gemeinsam. Hier simuliert ein direkt gesetzter
    Bestand die Arbeit anderer -- er muss den eigenen Zusatz ueberleben."""
    node = await repo.create_node(ordner.id, name="schlagworte.txt")
    fremd = await node.update(
        properties={"cclom:general_keyword": ["Fremdes Schlagwort", "Noch eines"]})
    assert set(fremd.keywords) == {"Fremdes Schlagwort", "Noch eines"}

    ergaenzt = await fremd.add_keywords("Weimar (Ort)")
    assert set(ergaenzt.keywords) == {"Fremdes Schlagwort", "Noch eines", "Weimar (Ort)"}

    bereinigt = await ergaenzt.remove_keywords("Weimar (Ort)")
    assert set(bereinigt.keywords) == {"Fremdes Schlagwort", "Noch eines"}


async def test_doppeltes_schlagwort_wird_nicht_zweimal_abgelegt(repo, ordner):
    node = await repo.create_node(ordner.id, name="doppelt.txt")
    einmal = await node.add_keywords("Physik")
    zweimal = await einmal.add_keywords("Physik")
    assert zweimal.keywords.count("Physik") == 1


# --- Dateien ---------------------------------------------------------------

INHALT = "Hallo aus der Bibliothek.\nZweite Zeile mit Umlaut: Größe.\n".encode()


async def test_datei_hoch_und_wieder_herunterladen(repo, ordner):
    """Die Rundreise muss byte-identisch sein -- sonst geht bei Umlauten oder
    Zeilenenden unbemerkt etwas verloren."""
    node = await repo.create_node(ordner.id, name="datei.txt", title="Mit Datei")
    mit_datei = await node.content.upload(
        INHALT, filename="datei.txt", mimetype="text/plain",
        version_comment="Testlauf")

    assert mit_datei.content.mimetype == "text/plain"
    assert mit_datei.content.size == len(INHALT)
    assert await mit_datei.content.download() == INHALT


async def test_das_download_servlet_liefert_nur_oeffentliches(repo, ordner):
    """Warum die drei Download-Tests hier rot sind -- gemessen, nicht vermutet.

    Am 10.09.2026 gegen Staging, alles am **selben** Knoten mit **derselben**
    Identitaet:

    * privat hochgeladen -> ``download()`` gibt 403, auch nach 69 Sekunden;
      es ist also keine Verzoegerung wie beim Suchindex
    * ``text()`` auf demselben privaten Knoten -> geht, 25 Zeichen
    * veroeffentlicht -> ``download()`` gibt die Bytes, angemeldet **und**
      anonym

    Daraus folgt: ``eduservlet/download`` authentifiziert gar nicht. Es
    liefert, was oeffentlich lesbar ist, und verweigert alles andere -- egal
    wer fragt. Das erklaert auch die aeltere Messung, dass ein anonymer und
    ein Basic-authentifizierter Aufruf byteweise dieselbe 403-Antwort
    bekommen: sie sind fuer das Servlet derselbe Aufruf.

    Die Bibliothek kann daran nichts aendern. Die Spec kennt kein ``GET`` fuer
    Binaerinhalt -- ``/node/v1/nodes/{repository}/{node}/content`` ist ``POST``
    --, ``downloadUrl`` ist der einzige Weg. Wer den Inhalt eines privaten
    Knotens braucht, nimmt ``text()``.

    Dieser Test faellt, wenn die Instanz das aendert. Genau dafuer steht er
    hier.
    """
    node = await repo.create_node(ordner.id, name="sichtbarkeit.txt")
    mit_datei = await node.content.upload(
        INHALT, filename="sichtbarkeit.txt", mimetype="text/plain")

    with pytest.raises(PermissionDeniedError):
        await mit_datei.content.download()
    # Derselbe Inhalt, anderer Weg -- der REST-Pfad kennt die Anmeldung.
    assert "Hallo aus der Bibliothek" in await mit_datei.content.text()

    await mit_datei.permissions.publish()
    veroeffentlicht = await repo.node(mit_datei.id)
    assert await veroeffentlicht.content.download() == INHALT, (
        "oeffentlich ist der einzige Zustand, in dem das Servlet liefert")


async def test_volltext_wird_extrahiert(repo, ordner):
    node = await repo.create_node(ordner.id, name="volltext.txt")
    mit_datei = await node.content.upload(
        INHALT, filename="volltext.txt", mimetype="text/plain")
    text = await mit_datei.content.text()
    assert "Hallo aus der Bibliothek" in text


async def test_knoten_ohne_datei_meldet_das_klar(repo, ordner):
    """Ein frisch angelegter Knoten hat keinen Binaerinhalt.

    Gemessen und dabei eine Annahme widerlegt: ``downloadUrl`` ist auch dann
    gesetzt, und ein GET darauf liefert **200 mit null Bytes** -- klaglos, und
    nicht von einer leeren Datei zu unterscheiden. Das verlaessliche Signal
    ist ``content.hash``.
    """
    from edusharing.errors import EduSharingError
    node = await repo.create_node(ordner.id, name="ohne-datei.txt")
    assert node.content.download_url, "downloadUrl ist auch ohne Inhalt gesetzt"
    assert node.content.has_content is False
    with pytest.raises(EduSharingError, match="carries no file"):
        await node.content.download()


async def test_leere_datei_gilt_als_inhalt(repo, ordner):
    """Der Fall, der cclom:size als Signal ausschliesst: eine 0-Byte-Datei hat
    dort ebenfalls None -- der Hash unterscheidet sie."""
    node = await repo.create_node(ordner.id, name="leer.txt")
    leer = await node.content.upload(b"", filename="leer.txt", mimetype="text/plain")
    assert leer.content.has_content is True
    assert leer.get("cclom:size") is None
    assert await leer.content.download() == b""


# --- Sammlungen ------------------------------------------------------------

@pytest.fixture
async def sammlung(repo):
    """Eine eigene, private Sammlung je Testlauf."""
    neu = await repo.create_collection(f"pytest-sammlung-{uuid.uuid4().hex[:8]}")
    assert neu.id
    try:
        yield neu
    finally:
        await _wegwerfen(neu)


async def test_sammlung_ist_privat(sammlung):
    """Die Vorgabe muss die engste sein -- eine versehentlich oeffentliche
    Sammlung sieht die ganze Instanz."""
    assert (sammlung.raw.get("collection") or {}).get("scope") == "MY"


async def test_inhalt_in_sammlung_legen_und_wieder_herausnehmen(repo, sammlung, ordner):
    """Angelegt wird eine Referenz, keine Kopie: das Original ueberlebt das
    Herausnehmen."""
    io = await repo.create_node(ordner.id, name="fuer-sammlung.txt", title="Referenzziel")

    assert await repo.add_to_collection(sammlung.id, io.id) is True
    await repo.remove_from_collection(sammlung.id, io.id)

    weiterhin_da = await repo.node(io.id)
    assert weiterhin_da.title == "Referenzziel"


async def test_doppeltes_einlegen_ist_kein_fehler(repo, sammlung, ordner):
    """409 heisst hier: liegt schon drin -- der gewuenschte Zustand. Ein Fehler
    daraus zu machen wuerde jeden Wiederholungslauf sprengen."""
    io = await repo.create_node(ordner.id, name="doppelt-eingelegt.txt")
    assert await repo.add_to_collection(sammlung.id, io.id) is True
    assert await repo.add_to_collection(sammlung.id, io.id) is False
    await repo.remove_from_collection(sammlung.id, io.id)


async def test_volltext_gibt_es_nicht_fuer_jeden_dateityp(repo, ordner):
    """Gemessen am 27.08.2026: Markdown und JSON liefern ueber textContent
    einen LEEREN String, waehrend download() die Bytes liefert.

    Das zaehlt fuer alles, was Anweisungen oder Daten als Markdown im
    Repositorium ablegt -- ein leerer Volltext sieht aus wie eine leere Datei.
    Der Test haelt die Eigenschaft fest, damit eine Aenderung der Instanz
    auffaellt statt still die Doku zu widerlegen.
    """
    proben = [
        ("klar.txt", "text/plain", b"Photosynthese im Klartext.", True),
        ("doku.md", "text/markdown", b"# Titel\n\nPhotosynthese.", False),
    ]
    for name, mimetype, inhalt, erwartet_text in proben:
        node = await repo.create_node(ordner.id, name=name, title=name)
        node = await node.content.upload(inhalt, filename=name, mimetype=mimetype)

        assert await node.content.download() == inhalt, f"{name}: Bytes verloren"

        volltext = await node.content.text()
        if erwartet_text:
            assert volltext, f"{name}: kein Volltext, obwohl erwartet"
        else:
            assert not volltext, (
                f"{name}: liefert jetzt Volltext -- die Instanz hat sich "
                "geaendert, der Docstring von NodeContent.text stimmt nicht mehr")


# --- Rueckleseprobe beim Anlegen ------------------------------------------


async def test_ordner_uebernimmt_beim_anlegen_keinen_eigenen_titel(repo, ordner):
    """Gemessen am 28.08.2026: legt man einen cm:folder mit cm:title an, setzt
    edu-sharing cm:title auf cm:name -- der mitgegebene Titel ist weg.

    Bei einem ccm:io kommt derselbe Titel an. Es ist also keine allgemeine
    Regel, sondern eine des Ordnertyps, und ohne die Rueckleseprobe beim
    Anlegen faellt sie niemandem auf.

    Nachtraeglich laesst sich der Titel sehr wohl setzen -- auch das hier
    geprueft, damit die Doku nicht mehr behauptet als gemessen ist.
    """
    with pytest.raises(SilentDropError) as fehler:
        await repo.create_node(
            ordner.id, name="mit-titel", type="cm:folder",
            properties={"cm:title": ["Ein eigener Titel"]})
    assert "cm:title" in fehler.value.dropped

    # Ohne Pruefung entsteht der Ordner, und der Titel ist der Name.
    unter = await repo.create_node(
        ordner.id, name="ohne-pruefung", type="cm:folder", verify=False,
        properties={"cm:title": ["Ein eigener Titel"]})
    frisch = await repo.node(unter.id)
    assert frisch.get("cm:title") == "ohne-pruefung"

    # Nachtraeglich geht es.
    geaendert = await frisch.update(properties={"cm:title": ["Nachgereicht"]})
    assert geaendert.get("cm:title") == "Nachgereicht"


async def test_abgeleitetes_feld_wird_beim_anlegen_gemeldet(repo, ordner):
    """ccm:oeh_lrt_aggregated leitet das Repositorium aus ccm:oeh_lrt ab und
    nimmt es nicht entgegen. Gemessen am 28.08.2026: die POST-Antwort zeigt das
    Feld gar nicht, waehrend ccm:taxonid im selben Aufruf ankommt.

    Ein halb geglueckter Schreibvorgang, der wie ein ganzer aussieht -- genau
    der Fall, fuer den es die Probe gibt.
    """
    aggregiert = await repo.vocab.resolve("ccm:oeh_lrt_aggregated", "Video")
    assert aggregiert, "Vorbedingung: der Wert laesst sich aufloesen"

    with pytest.raises(SilentDropError) as fehler:
        await repo.create_node(
            ordner.id, name="abgeleitet.txt",
            properties={"ccm:oeh_lrt_aggregated": [aggregiert]})
    assert "ccm:oeh_lrt_aggregated" in fehler.value.dropped


# --- Rechte und Veroeffentlichen ------------------------------------------
#
# Alles hier arbeitet ausschliesslich an selbst angelegten Knoten im eigenen
# Wegwerf-Ordner. Kein Test fasst fremde Rechte an.

async def test_frischer_knoten_ist_nicht_oeffentlich(knoten):
    """Die Vorbedingung fuer alles Weitere -- und der Grund, warum es diesen
    Teil gibt: was eine Anwendung anlegt, sieht zunaechst nur sie selbst."""
    assert not (await knoten.permissions.get()).is_public


async def test_veroeffentlichen_und_wieder_zuruecknehmen(knoten):
    assert await knoten.permissions.publish() is True
    assert (await knoten.permissions.get()).is_public

    assert await knoten.permissions.unpublish() is True
    assert not (await knoten.permissions.get()).is_public


async def test_veroeffentlichen_ist_wiederholbar(knoten):
    """Zweimal veroeffentlichen darf nicht zweimal schreiben -- ein zweiter
    Aufruf soll ein wiederholter Lauf sein duerfen, kein Fehler."""
    await knoten.permissions.publish()
    assert await knoten.permissions.publish() is False


async def test_zuruecknehmen_ist_wiederholbar(knoten):
    assert await knoten.permissions.unpublish() is False


async def test_veroeffentlichen_laesst_fremde_eintraege_stehen(repo, knoten):
    """Der POST ersetzt die lokale ACL. Wer nicht zusammenfuehrt, entzieht beim
    Veroeffentlichen anderen ihre Rechte -- unbemerkt, mit HTTP 200."""
    wer = await repo.whoami()
    await knoten.permissions.grant(wer.authority, "Coordinator")
    await knoten.permissions.publish()

    rechte = await knoten.permissions.get()
    assert rechte.allows(wer.authority, "Coordinator"), "eigener Eintrag verloren"
    assert rechte.is_public


async def test_recht_entziehen_laesst_die_uebrigen_stehen(repo, knoten):
    """Rot auf Staging, gemessen am 01.10.2026: das Entziehen des **eigenen**
    Eintrags wird nicht gespeichert -- Coordinator wie Consumer bleiben stehen,
    waehrend Vergeben und Veroeffentlichen ankommen. ``revoke`` meldet das als
    ``SilentDropError`` und eben nicht als Erfolg. Ob die Instanz damit ein
    Aussperren verhindert, ist von aussen nicht zu entscheiden; dieser Test
    faellt, solange es so ist."""
    wer = await repo.whoami()
    await knoten.permissions.grant(wer.authority, "Coordinator")
    await knoten.permissions.publish()

    await knoten.permissions.revoke(wer.authority, "Coordinator")
    rechte = await knoten.permissions.get()
    assert not rechte.allows(wer.authority, "Coordinator")
    assert rechte.is_public, "das Veroeffentlichen ist mit weggeflogen"


async def test_ein_zweiter_grant_behaelt_das_erste_recht(repo, knoten):
    """A01 an einer echten Instanz (Drittpruefung 10.09.2026).

    Die Wache, die diese Runde eingebaut hat, vergleicht die zurueckgelesenen
    Rechte **namentlich**. Fasste die Instanz Rollen zusammen -- speicherte
    etwa nur ``Coordinator`` und liesse das mitgesendete ``Consumer`` weg --,
    wuerde ein voellig berechtigter grant() jetzt SilentDropError werfen. Am
    Mock ist das nicht zu klaeren: dort speichert der Server, was der Test ihn
    speichern laesst.

    Gemessen am 10.09.2026 gegen Staging: nach dem ersten grant steht
    ``['Consumer']`` da, nach dem zweiten ``['Consumer', 'Coordinator']`` --
    exakt beide Namen, nichts zusammengefasst und nichts dazuerfunden.
    """
    wer = await repo.whoami()
    assert await knoten.permissions.grant(wer.authority, "Consumer") is True
    # Der zweite Aufruf sendet ``Consumer, Coordinator`` -- zusammengefuehrt,
    # nicht ersetzt. Genau hier hat die Pruefung bisher weggeschaut.
    assert await knoten.permissions.grant(wer.authority, "Coordinator") is True

    rechte = await knoten.permissions.get()
    eintrag = rechte.find(wer.authority)
    assert eintrag is not None, "der eigene Eintrag ist ganz verschwunden"
    # Namentlich und vollstaendig: faellt eine Instanz je darauf, Rollen
    # zusammenzufassen, faellt dieser Test und nicht erst ein Anwender.
    assert sorted(eintrag.permissions) == ["Consumer", "Coordinator"], (
        "die Instanz gibt den Eintrag nicht so zurueck, wie er gesendet wurde")


async def test_ein_grant_ohne_aenderung_schreibt_nicht(repo, knoten):
    """Die Gegenprobe: was schon dasteht, wird nicht noch einmal geschrieben --
    und die neue Wache aendert daran nichts."""
    wer = await repo.whoami()
    await knoten.permissions.grant(wer.authority, "Consumer")
    assert await knoten.permissions.grant(wer.authority, "Consumer") is False


async def test_unbekannte_gruppe_wird_still_verworfen(knoten):
    """Gemessen am 28.08.2026: HTTP 200, und danach steht nichts da. Dieselbe
    Klasse von Verlust wie bei den Properties, an einer anderen Stelle."""
    with pytest.raises(SilentDropError) as fehler:
        await knoten.permissions.grant("GROUP_gibtesnicht_xyz_9f3a", "Consumer")
    assert "GROUP_gibtesnicht_xyz_9f3a" in fehler.value.dropped


async def test_unbekannter_benutzer_wird_dagegen_gespeichert(knoten):
    """Die Kehrseite, und der Grund, warum der vorige Test eine Gruppe nimmt:
    Benutzernamen prueft das Repositorium nicht. Der Eintrag wird abgelegt und
    berechtigt niemanden -- die Rueckleseprobe kann einen Tippfehler im
    Benutzernamen also nicht auffangen. Das gehoert gesagt, statt es fuer
    abgedeckt zu halten."""
    assert await knoten.permissions.grant("gibtesnicht-xyz-9f3a", "Consumer") is True
    rechte = await knoten.permissions.get()
    assert rechte.allows("gibtesnicht-xyz-9f3a", "Consumer")


async def test_unbekanntes_recht_ist_dagegen_laut(repo, knoten):
    """Der Gegenbeweis zum vorigen Test: nicht alles an diesem Endpunkt ist
    still. Ein erfundener Rechtename kommt als 500 zurueck."""
    from edusharing.errors import ServerError
    wer = await repo.whoami()
    with pytest.raises(ServerError):
        await knoten.permissions.grant(wer.authority, "Quatschrecht")


# --- Vererbung -------------------------------------------------------------

async def test_kind_eines_oeffentlichen_ordners_ist_oeffentlich(repo, ordner):
    """Ohne eigenen Eintrag. Wer nur die lokale ACL liest, haelt einen fuer
    alle lesbaren Knoten fuer privat."""
    kind = await repo.create_node(ordner.id, name="geerbt.txt", title="Geerbt")
    await ordner.permissions.publish()

    rechte = await kind.permissions.get()
    assert rechte.own == (), "das Kind hat keinen eigenen Eintrag"
    assert rechte.is_public


async def test_zuruecknehmen_meldet_die_vererbung(repo, ordner):
    """Lokal gibt es nichts zu entfernen, und der Knoten bleibt oeffentlich.
    ``False`` zurueckzugeben hiesse behaupten, er sei jetzt privat."""
    from edusharing.errors import ConflictError
    kind = await repo.create_node(ordner.id, name="geerbt2.txt", title="Geerbt")
    await ordner.permissions.publish()

    with pytest.raises(ConflictError):
        await kind.permissions.unpublish()


# --- Wo ein Knoten liegt, und wer ihn kuratiert hat ------------------------

async def test_der_weg_nach_oben(repo, ordner):
    """Der Endpunkt liefert den Knoten selbst als ersten Eintrag -- gemessen.
    Die Bibliothek zieht ihn ab, sonst waere er sein eigener Vorfahre."""
    unter = await repo.create_node(ordner.id, name="unterordner", type="cm:folder")
    knoten = await repo.create_node(unter.id, name="tief.txt", title="Tief")

    eltern = await knoten.parents()
    assert [n.id for n in eltern] == [unter.id, ordner.id], "naechster zuerst"
    assert knoten.id not in [n.id for n in eltern]


async def test_die_vorfahren_tragen_ihre_namen(repo, ordner):
    """Ohne propertyFilter kommen sie mit leeren properties zurueck. Ein Pfad
    ohne Beschriftung ist als Brotkrume wertlos."""
    knoten = await repo.create_node(ordner.id, name="k.txt", title="K")
    eltern = await knoten.parents()
    assert eltern and eltern[0].name == ordner.name


async def test_sammlungen_eines_knotens(repo, ordner, sammlung):
    """Die andere Frage: nicht wo der Knoten liegt, sondern wer ihn eingelegt
    hat. Eine Sammlung haelt eine Referenz -- das Original bleibt, wo es ist."""
    knoten = await repo.create_node(ordner.id, name="kuratiert.txt", title="K")
    assert await knoten.collections() == []

    await repo.add_to_collection(sammlung.id, knoten.id)
    drin = await knoten.collections()
    assert [s.id for s in drin] == [sammlung.id]
    assert drin[0].title == sammlung.title, "der Eintrag traegt den ganzen Knoten"

    # Und das Elternteil ist davon unberuehrt.
    assert [n.id for n in await knoten.parents()] == [ordner.id]


async def test_placement_beantwortet_beides(repo, ordner, sammlung):
    knoten = await repo.create_node(ordner.id, name="verortet.txt", title="Verortet")
    await repo.add_to_collection(sammlung.id, knoten.id)

    ergebnis = await repo.flows.placement(knoten.id)
    assert ergebnis["title"] == "Verortet"
    assert [s["id"] for s in ergebnis["collections"]] == [sammlung.id]
    assert ergebnis["path"][-1]["id"] == ordner.id, "von oben nach unten"
    assert ergebnis["scope"], "der Endpunkt nennt, wie weit er reicht"


# --- Bewertungen und Kommentare -------------------------------------------
#
# Wieder nur an selbst angelegten Knoten im eigenen Wegwerf-Ordner.

async def test_frischer_knoten_ist_unbewertet(knoten):
    assert knoten.rating is None


async def test_bewerten_und_zuruecknehmen(knoten):
    bewertet = await knoten.rate(4, "Sehr brauchbar")
    assert bewertet is not None
    assert bewertet.average == 4.0
    assert bewertet.count == 1
    assert bewertet.own == 4.0

    assert await knoten.unrate() is None


async def test_die_null_wird_nicht_geschrieben(repo, knoten):
    """Gemessen: rating=0 zaehlt als abgegebene Null und zieht den Schnitt
    herunter, statt zurueckzunehmen. Die Bibliothek laesst sie nicht durch."""
    with pytest.raises(ValueError, match="unrate"):
        await knoten.rate(0)
    assert (await repo.node(knoten.id)).rating is None


async def test_bewerten_ist_wiederholbar(knoten):
    await knoten.rate(3)
    zweite = await knoten.rate(5)
    assert zweite.count == 1, "dieselbe Stimme, nicht eine zweite"
    assert zweite.own == 5.0


async def test_kommentar_schreiben_lesen_aendern_loeschen(knoten):
    assert await knoten.comments.list() == []

    neu = await knoten.comments.add("Ein Kommentar mit Umlauten: Groesse, Ubung")
    assert neu.text == "Ein Kommentar mit Umlauten: Groesse, Ubung"
    assert neu.author

    geaendert = await knoten.comments.edit(neu.id, "Nachgebessert")
    assert geaendert.text == "Nachgebessert"

    await knoten.comments.delete(neu.id)
    assert await knoten.comments.list() == []


async def test_der_text_kommt_ohne_anfuehrungszeichen_zurueck(knoten):
    """Der Kernfall: edu-sharing speichert den Body 1:1. Mit ``json=`` staende
    hier '"Erster"' statt 'Erster'."""
    neu = await knoten.comments.add("Erster")
    assert neu.text == "Erster"
    assert '"' not in neu.text


async def test_auf_einen_kommentar_antworten(knoten):
    frage = await knoten.comments.add("Eine Frage")
    antwort = await knoten.comments.add("Eine Antwort", reply_to=frage.id)
    assert antwort.reply_to == frage.id

    alle = await knoten.comments.list()
    assert {k.id for k in alle} == {frage.id, antwort.id}


# --- Vorschlaege und redaktionelle Einreichung -----------------------------

async def test_vorschlagen_und_entscheiden(repo, knoten):
    assert await knoten.suggestions.list() == []

    vorschlag = await knoten.suggestions.propose(
        "cclom:general_keyword", "Photosynthese",
        "Der Titel nennt das Thema", confidence=0.9)
    assert vorschlag.status == "PENDING"
    assert vorschlag.value == "Photosynthese"

    (gelesen,) = await knoten.suggestions.list()
    assert gelesen.id == vorschlag.id
    assert gelesen.why == "Der Titel nennt das Thema"


async def test_annehmen_traegt_den_wert_nicht_ein(repo, knoten):
    """Der Vorbehalt, live reproduziert. Der wlo-mcp-sc hat ihn am 01.08.2026
    gemessen, hier ist er noch einmal: nach ACCEPTED steht das Schlagwort
    nicht am Knoten. Wer glaubt, es stuende dort, hat einen Datensatz, der
    aussieht wie gepflegt und keiner ist."""
    vorschlag = await knoten.suggestions.propose(
        "cclom:general_keyword", "Photosynthese", "Weil")
    await knoten.suggestions.decide([vorschlag.id])

    frisch = await repo.node(knoten.id)
    assert frisch.keywords == [], "der Endpunkt wendet nichts an"

    (danach,) = await knoten.suggestions.list()
    assert danach.status == "ACCEPTED", "nur der Stand wandert"


async def test_ablehnen_setzt_den_anderen_stand(repo, knoten):
    vorschlag = await knoten.suggestions.propose("ccm:taxonid", "Biologie", "Weil")
    await knoten.suggestions.decide([vorschlag.id], accept=False)
    (danach,) = await knoten.suggestions.list()
    assert danach.status == "DECLINED"


async def test_einreichen_und_verlauf(repo, knoten):
    assert await knoten.workflow.history() == []

    wer = await repo.whoami()
    schritt = await knoten.workflow.submit(wer.authority, "100_tocheck",
                                           "Bitte pruefen")
    assert schritt.status == "100_tocheck"
    assert schritt.receivers == (wer.authority,)
    assert schritt.comment == "Bitte pruefen"
    assert schritt.editor == wer.authority

    verlauf = await knoten.workflow.history()
    assert len(verlauf) == 1


async def test_der_verlauf_kommt_neueste_zuerst(repo, knoten):
    """Der Verlauf ist ein Protokoll, kein Zustand -- jeder Schritt bleibt.
    Und er kommt in umgekehrter Reihenfolge zurueck: gemessen am 28.08.2026
    stand der zweite Schritt vorn. Darauf beruht die Rueckleseprobe von
    submit(), die den ersten Treffer nimmt."""
    wer = await repo.whoami()
    await knoten.workflow.submit(wer.authority, "100_tocheck", "Erst")
    await knoten.workflow.submit(wer.authority, "200_tosave", "Dann")
    verlauf = await knoten.workflow.history()
    assert [s.status for s in verlauf] == ["200_tosave", "100_tocheck"]
    assert verlauf[0].at >= verlauf[1].at


# --- Vorschaubild, Blaettern, Sammlung aendern -----------------------------

# Ein gueltiges 1x1-PNG, damit der Endpunkt etwas zu speichern hat.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082")


async def test_ein_frischer_knoten_hat_kein_eigenes_vorschaubild(knoten):
    """preview.url steht trotzdem da -- das Repositorium liefert ein
    Typ-Symbol. preview_url unterscheidet das."""
    assert knoten.preview_url is None
    assert (knoten.raw.get("preview") or {}).get("url"), "eine Adresse gibt es"


async def test_vorschaubild_setzen_und_loeschen(knoten):
    mit = await knoten.content.set_preview(PNG)
    assert mit.preview_url, "nach dem Setzen gibt es eine eigene Adresse"

    ohne = await mit.content.delete_preview()
    assert ohne.preview_url is None


async def test_blaettern_und_sortieren(repo, ordner):
    for i in range(3):
        await repo.create_node(ordner.id, name=f"s{i}.txt", title=f"Titel {i}")

    erste = await repo.nodes.children(ordner.id, limit=2)
    assert [n.name for n in erste.nodes] == ["s0.txt", "s1.txt"]
    assert erste.total == 3

    zweite = await repo.nodes.children(ordner.id, limit=2, offset=2)
    assert [n.name for n in zweite.nodes] == ["s2.txt"]
    assert zweite.offset == 2

    rueckwaerts = await repo.nodes.children(ordner.id, ascending=False)
    assert [n.name for n in rueckwaerts.nodes] == ["s2.txt", "s1.txt", "s0.txt"]


async def test_die_kinder_tragen_ihre_titel(repo, ordner):
    """Ohne propertyFilter kaemen sie ohne -- gemessen."""
    await repo.create_node(ordner.id, name="mit-titel.txt", title="Der Titel")
    seite = await repo.nodes.children(ordner.id)
    assert seite.nodes[0].title == "Der Titel"


async def test_sammlung_umbenennen(repo, sammlung):
    geaendert = await repo.collections.update(
        sammlung.id, title="Neuer Titel", description="Neue Beschreibung")
    assert geaendert.title == "Neuer Titel"
    assert geaendert.get("cm:description") == "Neue Beschreibung"
    assert geaendert.name == "Neuer Titel", "Umbenennen benennt auch den Knoten um"


async def test_nur_die_beschreibung_aendern(repo, sammlung):
    """title ist am Endpunkt Pflicht -- die Bibliothek liest den bestehenden
    und schickt ihn mit, statt in 'cmNameReadableName is null' zu laufen."""
    vorher = (await repo.node(sammlung.id)).title
    geaendert = await repo.collections.update(sammlung.id, description="Nur das")
    assert geaendert.title == vorher
    assert geaendert.get("cm:description") == "Nur das"


# --- Kuratierte Seiten -----------------------------------------------------
#
# Gebaut wird eine EIGENE Seite, nie eine bestehende angefasst: der Testzugang
# hat auf den Konfigurationsordner einer fremden Themenseite ohnehin kein
# Schreibrecht (gemessen 28.08.2026, ``can_write`` False), und die Umstellung
# waere sofort oeffentlich sichtbar.

def _variantendokument(ueberschrift: str) -> str:
    return json.dumps({
        "structure": {"swimlanes": [{
            "heading": ueberschrift, "type": "container",
            "grid": [{"cols": "6", "rows": "1", "item": "wlo-content-teaser"}],
        }]},
        "variables": {"virtual:profiling_widget_intention": "teach"},
    })


@pytest.fixture
async def eigene_seite(repo):
    """Sammlung, Konfigurationsordner und zwei Varianten -- alles selbst gebaut.

    Der Aufbau belegt nebenbei, dass die drei Eigenschaften des Page Builders
    ueber die Property-Route schreibbar sind: ``set_property`` liest jede
    zurueck und wuerde einen stillen Verlust melden.
    """
    marke = f"pytest-page-{uuid.uuid4().hex[:8]}"
    angelegt = []
    try:
        besitzer = await repo.create_collection(f"{marke}-seite")
        angelegt.append(besitzer)
        ordner = await repo.create_collection(f"PAGE_{marke}", parent=besitzer.id)
        angelegt.append(ordner)
        erste = await repo.create_collection(f"{marke}-A", parent=ordner.id)
        zweite = await repo.create_collection(f"{marke}-B", parent=ordner.id)
        angelegt += [erste, zweite]

        await erste.set_property("ccm:page_variant_config", _variantendokument("Lane A"))
        await zweite.set_property("ccm:page_variant_config", _variantendokument("Lane B"))
        await ordner.set_property("ccm:page_config", json.dumps({"variants": [
            f"workspace://SpacesStore/{erste.id}",
            f"workspace://SpacesStore/{zweite.id}"]}))
        await besitzer.set_property(
            "ccm:page_config_ref", f"workspace://SpacesStore/{ordner.id}")

        yield await repo.nodes.get(besitzer.id), erste.id, zweite.id
    finally:
        await _wegwerfen(*reversed(angelegt))


async def test_seite_wird_gelesen(eigene_seite):
    besitzer, erste, zweite = eigene_seite
    seite = await besitzer.page.get()
    assert seite is not None, "die eigene Seite wurde nicht gefunden"
    assert {v.id for v in seite.variants} == {erste, zweite}
    assert seite.by_position is True, "ohne default rendert die erste der Liste"
    assert seite.rendered.id == erste
    assert [ln.heading for ln in seite.rendered.swimlanes] == ["Lane A"]
    assert seite.rendered.intention == "teach"


async def test_variante_umstellen_und_zurueck(eigene_seite):
    besitzer, erste, zweite = eigene_seite
    umgestellt = await besitzer.page.render(zweite)
    assert umgestellt.rendered_id == zweite
    assert umgestellt.by_position is False
    assert umgestellt.rendered.swimlanes[0].heading == "Lane B"

    zurueck = await besitzer.page.render(erste)
    assert zurueck.rendered_id == erste


async def test_fremde_variante_wird_verweigert(eigene_seite):
    """Ein default ausserhalb von variants[] rendert nichts -- und die Instanz
    nimmt ihn gemessen ohne Widerspruch an."""
    besitzer, _, _ = eigene_seite
    with pytest.raises(ValueError):
        await besitzer.page.render("00000000-0000-0000-0000-000000000000")


async def test_sammlung_ohne_seite_meldet_das(sammlung):
    assert await sammlung.page.get() is None


# --- Schreiben ueber eine Listing-ID ---------------------------------------
#
# Vom MCP am 17.08.2026 gegen Staging gemessen: ein PUT an eine Referenz wird
# auf der Referenz gespeichert und erreicht das Original nie. Hier wird das
# Gegenteil belegt -- die Bibliothek leitet um und weist es aus -- und dass ein
# Loeschen an der Referenz das Original unangetastet laesst.
#
# Nicht ausgefuehrt am 02.09.2026: der temporaere Staging-Login wurde an dem
# Tag mit 401 abgelehnt. Laeuft mit dem naechsten gueltigen Konto.

async def test_schreiben_an_einer_listing_id_erreicht_das_original(repo, sammlung, knoten):
    assert await repo.add_to_collection(sammlung.id, knoten.id) is True
    inhalt = await repo.flows.collection_contents(sammlung.id, limit=10)
    eintrag = next(m for m in inhalt["materials"] if m["original_id"] == knoten.id)
    listing_id = eintrag["id"]
    assert listing_id != knoten.id, "das Listing liefert die Referenz, nicht den Datensatz"

    referenz = await repo.node(listing_id)
    assert referenz.is_reference
    assert referenz.original_id == knoten.id

    neu = await referenz.update(title="Ueber die Referenz geschrieben")
    assert neu.id == knoten.id
    assert neu.redirected_from == listing_id
    assert (await repo.node(knoten.id)).title == "Ueber die Referenz geschrieben"

    gegangen = await repo.flows.delete(listing_id)
    assert gegangen["is_reference"] is True
    assert gegangen["original_id"] == knoten.id
    assert (await repo.node(knoten.id)).title == "Ueber die Referenz geschrieben"
    danach = await repo.flows.collection_contents(sammlung.id, limit=10)
    assert all(m["id"] != listing_id for m in danach["materials"])


# --- Paket 3: Dubletten und Vorschlaege annehmen ----------------------------
#
# Nicht ausgefuehrt am 02.09.2026 (Staging-Login mit 401 abgelehnt).

async def test_zweites_material_zu_derselben_adresse_wird_nicht_angelegt(repo, ordner):
    """Die Pruefung sieht, was der Index sieht -- und der hinkt dem Anlegen nach.

    Gemessen am 02.09.2026 auf Staging: ein frisch angelegter Datensatz ist
    nach 5,3 s ueber ccm:wwwurl auffindbar, sofort nach dem Anlegen nicht.
    Ein zweiter Aufruf innerhalb dieser Spanne legt also einen zweiten
    Datensatz an; das ist die dokumentierte Grenze der Pruefung, kein
    Fehler. Der Test wartet deshalb auf den Index (bis 60 s) und belegt dann,
    dass der zweite Aufruf den ersten Datensatz zurueckgibt.
    """
    adresse = f"https://example.org/pytest-{uuid.uuid4().hex[:8]}"
    erstes = await repo.flows.add_material("Erstes", url=adresse, parent_id=ordner.id)
    assert erstes["created"] is True
    for _ in range(20):
        if await find_by_url(repo, adresse):
            break
        await asyncio.sleep(3)
    else:
        pytest.fail("nach 60 s nicht im Index -- die Pruefung kann den Datensatz nicht sehen")
    zweites = await repo.flows.add_material("Zweites", url=adresse, parent_id=ordner.id)
    assert zweites["created"] is False
    assert zweites["existing"]["id"] == erstes["id"]
    assert zweites["id"] == erstes["id"]


async def test_vorschlag_annehmen_schreibt_den_wert_wirklich(repo, knoten):
    vorschlag = await knoten.suggestions.propose(
        "cclom:general_keyword", "pytest-angenommen", "Test der Reihenfolge")
    got = await repo.flows.accept_suggestion(knoten.id, vorschlag.id)
    assert got["applied"] is True
    assert got["status"] == "ACCEPTED"
    assert "pytest-angenommen" in (await repo.node(knoten.id)).keywords
    offen = [s for s in await knoten.suggestions.list() if s.id == vorschlag.id]
    assert offen and offen[0].status == "ACCEPTED"


# --- COR-7: normalisiert die Instanz mehrwertige Eigenschaften? -----------

async def test_die_reihenfolge_mehrwertiger_eigenschaften_bleibt(repo, knoten):
    """Der Befund COR-7 haengt genau an dieser Frage.

    ``nodes_write.check`` vergleicht Listen **exakt**: gleiche Werte in
    gleicher Reihenfolge. Sortiert das Repositorium um, trimmt es oder
    normalisiert es Datumsangaben, dann meldet ein geglueckter Schreibvorgang
    einen stillen Verlust -- und der Aufrufer glaubt, seine Daten seien fort.

    Absichtlich absteigend geschrieben: eine aufsteigende Liste kaeme auch aus
    einer Sortierung unveraendert zurueck und bewiese nichts.
    """
    # ``verify=False`` und selbst nachladen: mit der Rueckleseprobe erzwingt
    # ``check()`` genau diese Gleichheit schon, ein umsortierender Server
    # flaege also als ``SilentDropError`` auf -- richtig rot, aber ohne die
    # Erklaerung, um die es hier geht. Und ohne die Probe gibt ``update``
    # den Knoten von **vor** dem Schreiben zurueck, liest also gar nichts
    # (nodes_write.py:169). Beides erst beim Ausfuehren gesehen (Pruefung
    # 09.09.2026).
    absteigend = ["Zebra", "Mitte", "Anfang"]
    await knoten.update(
        properties={"cclom:general_keyword": absteigend}, verify=False)
    gelesen = (await repo.node(knoten.id)).get_all("cclom:general_keyword")
    # Erst: ist ueberhaupt etwas angekommen? Ohne Rueckleseprobe faellt ein
    # stiller Verlust hier auf, und er liefert ``[]`` -- rot waere richtig,
    # aber die Meldung darunter nennt dann einen Grund, der nicht feststeht
    # (Pruefung 09.09.2026).
    assert len(gelesen) == len(absteigend), (
        f"geschrieben wurden {len(absteigend)} Schlagworte, gelesen "
        f"{gelesen!r} -- ueber die Reihenfolge sagt das nichts")
    assert gelesen == absteigend, (
        "die Instanz sortiert mehrwertige Eigenschaften um -- dann ist der "
        "exakte Vergleich in nodes_write.check zu streng (Audit COR-7)")


async def test_umgebende_leerzeichen_bleiben_stehen(repo, knoten):
    """Die zweite Haelfte derselben Frage: trimmt die Instanz?

    Die Bibliothek schreibt Schlagworte seit COR-8 selbst gestrippt; hier geht
    es um den direkten Weg ueber ``update``, der den Wert nimmt, wie er kommt.
    """
    await knoten.update(
        properties={"cclom:general_keyword": [" Rand "]}, verify=False)
    gelesen = (await repo.node(knoten.id)).get_all("cclom:general_keyword")
    assert gelesen, (
        "nichts angekommen -- ohne Rueckleseprobe faellt ein stiller Verlust "
        "hier auf; ueber das Trimmen sagt das nichts (Pruefung 09.09.2026)")
    assert gelesen == [" Rand "], (
        f"die Instanz veraendert den Wert: {gelesen!r} -- dann ist der exakte "
        "Vergleich zu streng (Audit COR-7)")


async def test_eine_gekuerzte_untersammlungsliste_meldet_sich_auch_live(repo, sammlung):
    """``collections_truncated`` gegen die Instanz, nicht gegen eine Attrappe.

    Drei Untersammlungen, zweimal gefragt: bei ``limit=2`` muss gekuerzt
    gemeldet werden und duerfen nur zwei herauskommen, bei ``limit=3`` nicht --
    sonst waere das Kennzeichen entweder blind oder immer wahr.

    **Was er nicht zeigt, und das ist gemessen:** den zusaetzlichen Datensatz
    aus ``maxItems=limit + 1``. Ihn zu entfernen laesst diesen Test gruen
    (Live-Mutation 09.09.2026) -- diese Instanz nennt eine richtige
    Gesamtzahl, und die traegt die Antwort hier allein. Der zusaetzliche
    Datensatz ist gegen Antworten da, die keine oder eine zu kleine Zahl
    nennen, und die kann kein Live-Test gegen einen ehrlichen Server
    herstellen. Was gegen ihn zu zeigen ist, zeigt der Test darunter: dass
    ``maxItems`` ueberhaupt mehr bringt, wenn man mehr verlangt.
    """
    unter = [await repo.create_collection(f"Unter {i}", parent=sammlung.id)
             for i in range(3)]
    try:
        gekuerzt = await repo.flows.collection_contents(sammlung.id, limit=2)
        ganz = await repo.flows.collection_contents(sammlung.id, limit=3)
    finally:
        await _wegwerfen(*unter)

    assert gekuerzt["returned_collections"] == 2, "ausgeliefert wird das Limit"
    assert len(gekuerzt["collections"]) == 2, "der eine mehr geht nicht raus"
    assert gekuerzt["collections_truncated"] is True

    assert ganz["returned_collections"] == 3
    assert ganz["collections_truncated"] is False, (
        "drei von dreien sind alle -- ein Kennzeichen, das immer wahr ist, "
        "sagt so wenig wie eines, das immer falsch ist")


async def test_der_endpunkt_liefert_so_viele_wie_verlangt(repo, sammlung):
    """Die Annahme, auf der der ganze Deckel-Zug ruht.

    ``page_cut`` fragt ``limit + 1`` an und liest die Antwort daran, ob der
    eine zusaetzliche Datensatz ankommt. Das setzt voraus, dass der Endpunkt
    ``maxItems`` **beachtet** und nicht bei einer eigenen Zahl deckelt.

    Gemessen am 09.09.2026 an einem Wegwerf-Ordner mit 205 Kindern
    (``maxItems=201`` -> 201 Datensaetze) und an einer Wegwerf-Sammlung mit
    sechs Untersammlungen. Eine Messung, die niemand wiederholt, verfaellt --
    darum steht sie hier als Wache: deckelt die Instanz eines Tages doch, wird
    sie rot, und der Zug ist sichtbar auf Sand gebaut.
    """
    for i in range(3):
        await repo.create_collection(f"Unter {i}", parent=sammlung.id)
    geliefert = {}
    for gefragt in (1, 2, 3, 4):
        antwort = await repo.raw.json(
            "GET",
            f"/collection/v1/collections/-home-/{sammlung.id}/children/collections",
            params={"maxItems": gefragt})
        geliefert[gefragt] = len(antwort.get("collections") or [])
    assert geliefert == {1: 1, 2: 2, 3: 3, 4: 3}, geliefert
