"""Normalisierung der Repository-URL.

Die behandelten Eingabeformen sind keine erfundenen Randfaelle: es sind die
Formen, in denen Betreibende ihre Repository-Adresse tatsaechlich weitergeben
-- mal die blanke Domain, mal ein aus der REST-Doku kopierter Pfad.
"""

import pytest

from edusharing.errors import EduSharingError
from edusharing.urls import (
    is_unroutable_host,
    mask_userinfo,
    normalize_repository_url,
    path_segment,
    refuse_userinfo,
    rest_base,
    unsafe_url_reason,
)

HOST = "https://repositorium.example.test"
FULL = f"{HOST}/edu-sharing"


@pytest.mark.parametrize("eingabe", [
    HOST,                                   # blanke Domain
    f"{HOST}/",                             # mit Schraegstrich
    FULL,                                   # schon vollstaendig
    f"{FULL}/",
    f"{FULL}//",                            # mehrfacher Schraegstrich
    f"{FULL}/rest",                         # aus der REST-Doku kopiert
    f"{FULL}/rest/",
    f"  {FULL}  ",                          # aus der Zwischenablage
    "repositorium.example.test",            # ohne Protokoll
])
def test_alle_schreibweisen_ergeben_dieselbe_basis(eingabe):
    assert normalize_repository_url(eingabe) == FULL


def test_http_bleibt_http():
    """Lokale und interne Instanzen laufen ohne TLS. Ein erzwungenes Upgrade
    auf https wuerde sie unerreichbar machen."""
    assert normalize_repository_url("http://localhost:8080") == "http://localhost:8080/edu-sharing"


def test_pfad_unterhalb_von_edu_sharing_bleibt_erhalten():
    """Manche Instanzen liegen nicht auf der Wurzel."""
    assert normalize_repository_url("https://host.test/repo/edu-sharing") == \
        "https://host.test/repo/edu-sharing"


def test_rest_basis_wird_angehaengt():
    assert rest_base(FULL) == f"{FULL}/rest"


# --- Eingaben, die ein Konfigurationsfehler sind --------------------------

def test_leere_eingabe_wird_abgelehnt():
    """Sonst richtet sich die Anwendung stillschweigend gegen "https:///edu-sharing"."""
    with pytest.raises(EduSharingError):
        normalize_repository_url("")


def test_nur_leerzeichen_wird_abgelehnt():
    with pytest.raises(EduSharingError):
        normalize_repository_url("   ")


def test_deep_link_wird_abgelehnt():
    """Ein aus dem Browser kopierter Link auf eine Seite, nicht auf das
    Repositorium. Ohne Pruefung wuerde jeder Aufruf mit 404 enden, und die
    Ursache stuende nirgends."""
    with pytest.raises(EduSharingError, match="components"):
        normalize_repository_url(f"{FULL}/components/render/abc-123")


def test_doppeltes_edu_sharing_wird_abgelehnt():
    with pytest.raises(EduSharingError, match="edu-sharing"):
        normalize_repository_url(f"{FULL}/edu-sharing")


@pytest.mark.parametrize("eingabe", [
    "https://alice:geheim@repositorium.example.test",
    "alice:geheim@repositorium.example.test/edu-sharing",     # ohne Schema
    "https://alice@repositorium.example.test/edu-sharing",    # nur der Name
    "https:/alice:geheim@repositorium.example.test",          # Tippfehler im Schema
    "ftp://alice:geheim@repositorium.example.test",           # fremdes Schema
])
def test_zugangsdaten_in_der_adresse_werden_abgewiesen(eingabe):
    """Audit SEC-1 (03.09.2026): ``user:pw@host`` ging durch -- und die
    Adresse steht in jedem Log, jeder Viewer-URL, jeder Fehlermeldung. Die
    Meldung nennt den richtigen Ort und wiederholt das Passwort nicht."""
    with pytest.raises(EduSharingError, match="auth=") as fehler:
        normalize_repository_url(eingabe)
    assert "geheim" not in str(fehler.value)
    assert "EDU_SHARING_USER" in str(fehler.value)


@pytest.mark.parametrize("eingabe", [
    "ftp://repositorium.example.test/edu-sharing",
    "https:/repositorium.example.test",
    "file:///tmp/edu-sharing",
])
def test_ein_fremdes_oder_verschriebenes_schema_wird_abgewiesen(eingabe):
    """Review 06.09.2026 (F1): "https:/host" bekam "https://" vorangestellt und
    wurde zu "https://https:/host" -- mit allem, was hinter dem Tippfehler
    stand, im Pfad. Nur http(s) ist eine Repository-Adresse."""
    with pytest.raises(EduSharingError, match="http"):
        normalize_repository_url(eingabe)


def test_ein_port_ist_kein_schema():
    assert (normalize_repository_url("repositorium.example.test:8080")
            == "https://repositorium.example.test:8080/edu-sharing")


def test_refuse_userinfo_liest_die_autoritaet_nicht_urlsplit():
    """urlsplit sieht in "user:pw@host" das Schema "user" und in
    "https:/user:pw@host" den Pfad -- die Zugangsdaten stuenden dann trotzdem
    in jeder Logzeile. Gelesen wird, was hinter Schema und Schraegstrichen bis
    zum ersten "/" steht."""
    for adresse in ("alice:geheim@host.test", "https:/alice:geheim@host.test",
                    "//alice:geheim@host.test", "alice@host.test"):
        with pytest.raises(EduSharingError) as fehler:
            refuse_userinfo(adresse, instead="x")
        assert "geheim" not in str(fehler.value), adresse
    for harmlos in ("https://host.test/pfad@x", "host.test:8080/a?b=c@d", ""):
        refuse_userinfo(harmlos, instead="x")


def test_mask_userinfo_verbirgt_nur_die_zugangsdaten():
    assert mask_userinfo("https:/alice:geheim@host.test/x") == "https:/***@host.test/x"
    assert mask_userinfo("https://host.test/x") == "https://host.test/x"


def test_mask_userinfo_bleibt_bei_langen_adressen_linear():
    """Gefunden beim Schliessen von Audit SEC-23-1, dieselbe Klasse: das Muster
    begann in einem langen Lauf ohne ``@`` an jeder Stelle neu und las den Rest
    des Laufs jedes Mal wieder. Gemessen am 23.09.2026: 16 000 Zeichen 1,2 s --
    und ``agent.check_url`` maskiert so jede Adresse, die es ablehnt, also
    gerade die aus fremden Datensaetzen."""
    import time
    lang = "ftp://" + "a" * 60_000
    start = time.perf_counter()
    assert mask_userinfo(lang) == lang
    assert mask_userinfo(lang + "@host") == "ftp://***@host"
    assert time.perf_counter() - start < 3.0


def test_zugangsdaten_werden_vor_dem_deep_link_geprueft():
    """Sonst wiederholte die Deep-Link-Meldung die Adresse samt Passwort."""
    with pytest.raises(EduSharingError) as fehler:
        normalize_repository_url(
            "https://alice:geheim@repositorium.example.test/edu-sharing/components/render/x"
        )
    assert "geheim" not in str(fehler.value)


# --- Pfadsegmente ---------------------------------------------------------
#
# Diese Gruppe existiert wegen eines Audit-Befundes (F1, 27.08.2026): Bezeichner
# wurden unkodiert per f-String in Pfade gesetzt. Nachgewiesen war, dass eine
# node_id von "../../../admin/v1/applications" einen anderen Endpunkt erreicht
# und "abc?admin=1" das angehaengte "/metadata" verschluckt.
#
# Der Fall ist keine Theorie: in einem MCP-Server kommt die node_id aus dem
# Sprachmodell und damit aus Fremddaten.

def test_pfadsegment_kodiert_schraegstrich():
    """Ein Segment darf niemals eine Pfadgrenze ueberschreiten."""
    assert path_segment("a/b") == "a%2Fb"


def test_pfadsegment_kodiert_punkte_und_trenner():
    assert path_segment("../../admin") == "..%2F..%2Fadmin"
    assert path_segment("abc?admin=1") == "abc%3Fadmin%3D1"
    assert path_segment("abc#frag") == "abc%23frag"


def test_pfadsegment_laesst_harmlose_ids_unveraendert():
    """Gegenprobe: echte edu-sharing-IDs sind UUIDs und duerfen sich nicht
    aendern -- sonst bricht die Kodierung den Normalbetrieb."""
    uuid = "8f3c1e42-9b7a-4d21-bc55-0e6a1f2d3c47"
    assert path_segment(uuid) == uuid
    assert path_segment("-home-") == "-home-"
    assert path_segment("mds_oeh") == "mds_oeh"


def test_pfadsegment_kodiert_umlaute():
    assert path_segment("Bücher") == "B%C3%BCcher"


def test_pfadsegment_lehnt_leeres_ab():
    """Ein leeres Segment erzeugt einen doppelten Schraegstrich und damit einen
    voellig anderen Pfad."""
    with pytest.raises(EduSharingError):
        path_segment("")


# --- is_unroutable_host ---------------------------------------------------
# Die eine Stelle, an der entschieden wird, ob eine Adresse abgerufen werden
# darf. Sie stand bis zum 28.08.2026 doppelt in der Bibliothek, und die zwei
# Fassungen antworteten verschieden (Audit A6).

@pytest.mark.parametrize("host", [
    "93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111",
])
def test_oeffentliche_adressen_sind_routbar(host):
    """Die Gegenprobe, die beim Zusammenlegen gefehlt hat: die Formpruefung
    fuer ungewoehnliche Schreibweisen trifft auf **jede** punktierte IPv4 zu --
    ihr letztes Label besteht immer aus Ziffern. Unbedingt aufgerufen sperrte
    sie den gesamten oeffentlichen IPv4-Raum aus. Sie darf deshalb nur laufen,
    wenn ``ipaddress`` den Host gar nicht lesen konnte.
    """
    assert is_unroutable_host(host) is False


@pytest.mark.parametrize("host", [
    "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",
    "::1", "[::1]", "fc00::1",
    "100.64.0.1",     # CGNAT -- nur `not is_global` faengt das
    "64:ff9b::1",     # NAT64 -- nur die Aufzaehlung faengt das
    "2130706433", "0x7f000001", "127.1",   # andere Schreibweisen (A7)
])
def test_nicht_routbare_adressen_werden_erkannt(host):
    assert is_unroutable_host(host) is True


@pytest.mark.parametrize("host", ["example.com", "sub.example.org", "localhost"])
def test_namen_werden_hier_nicht_beurteilt(host):
    """Was ein Name aufloest, entscheidet der Resolver -- und muss danach noch
    einmal geprueft werden. ``localhost`` sperrt ``agent.safety`` ueber seine
    Namensliste, nicht hier."""
    assert is_unroutable_host(host) is False


# --- SEC-3: ein Backslash bringt zwei Parser auseinander -----------------


@pytest.mark.parametrize("adresse", [
    "http://example.com\\evil.test/",
    "https://example.org\\..\\pfad",
])
def test_ein_backslash_macht_die_adresse_unsicher(adresse):
    """Ein Backslash gehoert in keine Adresse: WHATWG liest ihn wie einen
    Schraegstrich, ``urlsplit`` nicht. Wo die beiden auseinandergehen, prueft
    man nicht mehr, was spaeter geholt wird (Audit SEC-3)."""
    assert unsafe_url_reason(adresse) is not None
    assert "backslash" in unsafe_url_reason(adresse)


def test_ein_prozentkodierter_backslash_bleibt_erlaubt():
    """Die Gegenprobe: kodiert ist er ein Zeichen im Pfad, kein Trenner."""
    assert unsafe_url_reason("https://example.org/pfad%5Cdatei") is None


# --- F07: die beiden Werte, die selbst Pfadgrenzen sind --------------------

@pytest.mark.parametrize("punkt", [".", ".."])
def test_punktsegmente_werden_abgelehnt(punkt):
    """``quote`` laesst sie unveraendert -- sie sind unreserviert. Erst httpx
    normalisiert sie beim Bauen der URL weg, und die Anfrage erreicht einen
    anderen Endpunkt als den gefragten."""
    with pytest.raises(EduSharingError):
        path_segment(punkt)


@pytest.mark.parametrize("harmlos", ["a.b", "...", ".gitignore", "abc.", "a..b"])
def test_punkte_im_bezeichner_bleiben_erlaubt(harmlos):
    """Die Gegenprobe: nur die beiden ganzen Segmente normalisieren etwas
    weg. Ein Punkt *im* Bezeichner tut es nicht, und ihn abzulehnen waere eine
    Regel gegen gueltige IDs."""
    assert path_segment(harmlos) == harmlos


@pytest.mark.parametrize("eingabe", [
    f"{HOST}/?locale=de",
    f"{HOST}#anker",
    f"{FULL}?locale=de",
    f"{HOST}/rest?x=1",
])
def test_query_und_fragment_werden_abgewiesen(eingabe):
    """Gemessen (Audit COR-20-2): ``.../edu-sharing?x=1`` wurde zu
    ``.../edu-sharing?x=1/edu-sharing`` -- genau die Verdopplung, die diese
    Funktion sonst verweigert. Der Zaehler liest ``(?=/|$)``, und ein ``?``
    ist fuer ihn kein Segmentende. Alles danach geht an eine Adresse, die nie
    antworten kann, und nichts sagte warum.
    """
    with pytest.raises(EduSharingError):
        normalize_repository_url(eingabe)
