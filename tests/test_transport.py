"""Der eine Weg nach draussen.

Drei Dinge werden hier geprueft, weil sie sonst niemand prueft: dass das
Passwort nur an das konfigurierte Repositorium geht, dass eine Anfrage nur
dann wiederholt wird, wenn eine Wiederholung ueberhaupt gelingen kann, und
dass die Gleichzeitigkeit begrenzt bleibt.
"""

import asyncio
import gzip
import json
import random

import httpx
import pytest

from edusharing.auth import ANONYMOUS, BasicCredential
from edusharing.errors import (
    AuthenticationError,
    ContentTooLargeError,
    EduSharingError,
    NotFoundError,
    RateLimitedError,
    ServerError,
    TransportError,
)
from edusharing.transport import DEFAULT_TIMEOUT, Transport

REPO = "https://repositorium.example.test/edu-sharing"
CRED = BasicCredential("alice", "geheim")


def _transport(handler, **kwargs):
    """Transport mit einem Handler statt echtem Netz. Backoff auf 0, damit die
    Tests nicht auf Wartezeiten warten."""
    kwargs.setdefault("credential", CRED)
    kwargs.setdefault("backoff_base", 0.0)
    return Transport(
        REPO,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def _ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


# --- Wohin das Passwort geht ----------------------------------------------

async def test_auth_geht_an_das_repositorium():
    gesehen = {}

    def handler(request):
        gesehen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={})

    async with _transport(handler) as t:
        await t.request("GET", "/_about")
    assert gesehen["auth"] is not None
    assert gesehen["auth"].startswith("Basic ")


async def test_auth_geht_nicht_an_fremde_hosts():
    """Absolute URLs kommen auch aus Antwortdaten -- eine Vorschau-URL etwa.
    Wenn eine davon woanders hinzeigt, darf das Passwort nicht mitgehen."""
    gesehen = {}

    def handler(request):
        gesehen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"")

    async with _transport(handler) as t:
        await t.request("GET", "https://fremder-host.test/etwas")
    assert gesehen["auth"] is None


async def test_auth_geht_nicht_an_aehnlich_aussehende_hosts():
    """Ein blosser Praefix-Vergleich wuerde hier zuschlagen: die fremde Adresse
    beginnt exakt mit der eigenen."""
    gesehen = {}

    def handler(request):
        gesehen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"")

    async with _transport(handler) as t:
        await t.request("GET", f"{REPO}.angreifer.test/etwas")
    assert gesehen["auth"] is None


async def test_relative_pfade_gehen_an_die_rest_basis():
    gesehen = {}

    def handler(request):
        gesehen["url"] = str(request.url)
        return httpx.Response(200, json={})

    async with _transport(handler) as t:
        await t.request("GET", "/_about")
    assert gesehen["url"] == f"{REPO}/rest/_about"


async def test_zugangsdaten_pro_anfrage_ueberschreibbar():
    """Ein Dienst, der viele Nutzende bedient, braucht das pro Anfrage --
    ein globaler Zustand wuerde Anfragen vermischen."""
    gesehen = []

    def handler(request):
        gesehen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={})

    async with _transport(handler) as t:
        await t.request("GET", "/_about")
        await t.request("GET", "/_about", credential=ANONYMOUS)
        await t.request("GET", "/_about", credential=BasicCredential("bob", "x"))
    assert gesehen[0] is not None
    assert gesehen[1] is None
    assert gesehen[2] is not None
    assert gesehen[0] != gesehen[2]


# --- Was wiederholt wird, und was nicht -----------------------------------

async def test_502_wird_wiederholt():
    """Cloudflare-Timeouts und Saettigung stromaufwaerts sind voruebergehend."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(502, content=b"<html>error code: 522</html>")

    async with _transport(handler, max_retries=2) as t:
        with pytest.raises(ServerError):
            await t.request("GET", "/_about")
    assert len(versuche) == 3          # ein Versuch + zwei Wiederholungen


async def test_erfolg_nach_wiederholung():
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) < 3:
            return httpx.Response(503, content=b"")
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, max_retries=3) as t:
        antwort = await t.request("GET", "/_about")
    assert antwort.status_code == 200
    assert len(versuche) == 3


async def test_500_not_allowed_for_guest_wird_nicht_wiederholt():
    """Der Kernfall. Gemessen: fehlende Anmeldung kommt als HTTP 500 mit
    "Not allowed for guest user". Ein Retry darauf ist dreimal dieselbe
    Anfrage, die nie gelingen kann -- und dreimal Last auf einem
    Repositorium, das gar nichts falsch gemacht hat."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(500, json={
            "error": "java.lang.Exception",
            "message": "Not allowed for guest user",
        })

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(AuthenticationError):
            await t.request("GET", "/iam/v1/people/-home-/-me-/preferences")
    assert len(versuche) == 1


@pytest.mark.parametrize("status", [400, 403, 404, 409])
async def test_fehler_der_anfrage_werden_nicht_wiederholt(status):
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(status, json={"error": "x", "message": "y"})

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(EduSharingError):
            await t.request("GET", "/_about")
    assert len(versuche) == 1


async def test_404_ergibt_notfounderror():
    def handler(request):
        return httpx.Response(404, json={
            "error": "org.edu_sharing.restservices.DAOMissingException",
            "message": "Node does not exist",
        })

    async with _transport(handler) as t:
        with pytest.raises(NotFoundError):
            await t.request("GET", "/node/v1/nodes/-home-/x/metadata")


# --- Netzwerkfehler -------------------------------------------------------

async def test_timeout_wird_transport_error():
    """Abgegrenzt von ServerError: bei einem Timeout ist unklar, ob etwas
    passiert ist. Fuer einen Schreibvorgang ist das ein Unterschied."""
    def handler(request):
        raise httpx.ReadTimeout("zu langsam", request=request)

    async with _transport(handler, max_retries=1) as t:
        with pytest.raises(TransportError):
            await t.request("GET", "/_about")


async def test_timeout_wird_wiederholt():
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) < 2:
            raise httpx.ConnectError("weg", request=request)
        return httpx.Response(200, json={})

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("GET", "/_about")
    assert antwort.status_code == 200
    assert len(versuche) == 2


# --- Was nach dem Senden wiederholt werden darf ----------------------------
#
# Audit-Befund COR-1 (03.09.2026): ein Timeout nach dem Senden und ein 5xx
# lassen offen, ob der Server die Anfrage ausgefuehrt hat. Ein zweites POST
# legt dann ein zweites Kind an, haengt ein zweites Schlagwort an. Vor dem
# Senden ist dagegen nichts passiert -- da darf jede Methode nochmal.

WRITE = "/node/v1/nodes/-home-/abc/children"


def _erst_scheitern(fehler):
    """Handler, der beim ersten Aufruf scheitert -- mit einem Status (int)
    oder einer httpx-Ausnahme (Klasse) -- und danach 200 sagt."""
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) < 2:
            if isinstance(fehler, int):
                return httpx.Response(fehler, text="")
            raise fehler("scheitert", request=request)
        return httpx.Response(200, json={})

    return handler, versuche


async def test_ein_post_wird_nach_lesetimeout_nicht_wiederholt():
    """Nach dem Senden weiss niemand, ob das Kind schon angelegt ist. Die
    Meldung sagt das, damit der Aufrufer nachsieht statt nochmal zu senden."""
    handler, versuche = _erst_scheitern(httpx.ReadTimeout)

    async with _transport(handler, max_retries=2) as t:
        with pytest.raises(TransportError, match="may already have been carried out"):
            await t.request("POST", WRITE)
    assert len(versuche) == 1


async def test_ein_post_wird_nach_5xx_nicht_wiederholt():
    handler, versuche = _erst_scheitern(502)

    async with _transport(handler, max_retries=2) as t:
        with pytest.raises(ServerError):
            await t.request("POST", WRITE)
    assert len(versuche) == 1


async def test_ein_delete_wird_nach_lesetimeout_nicht_wiederholt():
    """Ein zweites DELETE liefe in ein 404, das der Aufrufer fuer die Wahrheit
    hielte: "gab es nie" statt "ist gerade weg"."""
    handler, versuche = _erst_scheitern(httpx.ReadTimeout)

    async with _transport(handler, max_retries=2) as t:
        with pytest.raises(TransportError):
            await t.request("DELETE", "/node/v1/nodes/-home-/abc")
    assert len(versuche) == 1


async def test_ein_verbindungsfehler_wird_auch_bei_post_wiederholt():
    handler, versuche = _erst_scheitern(httpx.ConnectError)

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("POST", WRITE)
    assert antwort.status_code == 200
    assert len(versuche) == 2


async def test_ein_get_wird_nach_lesetimeout_weiter_wiederholt():
    handler, versuche = _erst_scheitern(httpx.ReadTimeout)

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("GET", "/_about")
    assert antwort.status_code == 200
    assert len(versuche) == 2


async def test_als_idempotent_markiert_wird_auch_ein_post_wiederholt():
    """Eine Eigenschaft setzen, eine ACL ersetzen: doppelt angekommen ist
    derselbe Zustand. Solche Aufrufe sagen es dem Transport selbst."""
    handler, versuche = _erst_scheitern(httpx.ReadTimeout)

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request(
            "POST", "/node/v1/nodes/-home-/abc/property", idempotent=True
        )
    assert antwort.status_code == 200
    assert len(versuche) == 2


async def test_ein_401_wird_auch_bei_post_einmal_wiederholt():
    """Abgelehnt, bevor etwas ausgefuehrt wurde -- die gemessene 401-Laune
    (README) trifft Schreibvorgaenge genauso, und die Wiederholung bleibt
    ungefaehrlich."""
    handler, versuche = _erst_scheitern(401)

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("POST", WRITE)
    assert antwort.status_code == 200
    assert len(versuche) == 2


# --- Gleichzeitigkeit -----------------------------------------------------

async def test_gleichzeitigkeit_ist_begrenzt():
    """Ohne Begrenzung erschlaegt ein Fan-out ueber viele Knoten das
    Repositorium -- gemessen liegt dessen Grenze niedriger, als eine
    unbegrenzte Schleife erzeugt."""
    laufend = 0
    hoechststand = 0

    async def handler(request):
        nonlocal laufend, hoechststand
        laufend += 1
        hoechststand = max(hoechststand, laufend)
        await asyncio.sleep(0.01)
        laufend -= 1
        return httpx.Response(200, json={})

    async with _transport(handler, max_concurrency=3) as t:
        await asyncio.gather(*(t.request("GET", "/_about") for _ in range(12)))
    assert hoechststand <= 3


# --- JSON-Bequemlichkeit --------------------------------------------------

async def test_json_gibt_den_geparsten_koerper():
    async with _transport(lambda r: httpx.Response(200, json={"a": 1})) as t:
        assert await t.json("GET", "/_about") == {"a": 1}


# --- Der eine 401, der doch wiederholt wird -------------------------------
#
# 401 stand bis zum 28.08.2026 in der Liste oben. Er steht dort nicht mehr,
# weil die Liste zwei Behauptungen in einer war. Gemessen gegen Staging mit
# gueltiger Anmeldung, 20 Knoten je Runde, 5 Runden:
#
#     nacheinander   0 von 100 Anfragen mit 401
#     gleichzeitig   9 von 100 Anfragen mit 401
#
# Dieselben Knoten, dieselben Zugangsdaten. Ein 401 unter Gleichzeitigkeit ist
# also keine Aussage ueber die Zugangsdaten, sondern ueber den Moment -- und er
# trifft jeden Stapel-Ablauf dieser Bibliothek.

async def test_401_mit_anmeldung_wird_einmal_wiederholt():
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) == 1:
            return httpx.Response(401, json={"error": "x", "message": "nope"})
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, max_retries=3) as t:
        antwort = await t.request("GET", "/_about")
    assert antwort.status_code == 200
    assert len(versuche) == 2


async def test_401_wird_hoechstens_einmal_wiederholt():
    """Falsche Zugangsdaten duerfen nicht max_retries mal kosten -- ein
    zusaetzlicher Versuch ist der Preis fuer den gemessenen Ausrutscher, drei
    waeren eine Strafe fuer einen Tippfehler im Passwort."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(401, json={"error": "x", "message": "nope"})

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(AuthenticationError):
            await t.request("GET", "/_about")
    assert len(versuche) == 2


async def test_401_ohne_wiederholungsbudget_bleibt_bei_einem_versuch():
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(401, json={"error": "x", "message": "nope"})

    async with _transport(handler, max_retries=0) as t:
        with pytest.raises(AuthenticationError):
            await t.request("GET", "/_about")
    assert len(versuche) == 1


async def test_401_ohne_anmeldung_wird_nicht_wiederholt():
    """Anonym heisst 401 "hierfuer braucht es eine Anmeldung". Das wird beim
    zweiten Mal nicht anders."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(401, json={"error": "x", "message": "nope"})

    async with _transport(handler, credential=ANONYMOUS, max_retries=3) as t:
        with pytest.raises(AuthenticationError):
            await t.request("GET", "/_about")
    assert len(versuche) == 1


async def test_als_401_verkleideter_500_wird_nicht_wiederholt():
    """Der gemessene Ausrutscher ist ein echter 401-Status. Das "Not allowed
    for guest" im 500er ist eine Aussage ueber die Anmeldung und bleibt bei
    einem Versuch -- sonst waere der Sinn der Uebersetzung wieder dahin."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(500, json={
            "error": "java.lang.Exception",
            "message": "Not allowed for guest user",
        })

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(AuthenticationError):
            await t.request("GET", "/_about")
    assert len(versuche) == 1


# --- Umleitungen (Audit A8) -----------------------------------------------

async def test_eine_umleitung_ist_kein_erfolg():
    """``status_code < 400`` liess jede 3xx als Erfolg durch. Dieser Client
    folgt Umleitungen nicht -- ``follow_redirects`` bleibt bei der Vorgabe
    ``False`` --, also kam der leere Koerper der Umleitung zurueck. Bei
    ``Content.download`` sind das null Bytes statt der Datei, still.

    Gemessen am 28.08.2026 gegen Staging: acht Downloads, null Umleitungen --
    auf dieser Instanz also nicht ausgeloest. Hinter einem Proxy, der auf eine
    Anmeldeseite umlenkt, oder bei Inhalten von einem CDN schon.
    """
    def handler(_request):
        return httpx.Response(302, headers={"Location": "https://cdn.test/datei.pdf"})

    async with _transport(handler) as t:
        with pytest.raises(EduSharingError) as info:
            await t.request("GET", "/node/v1/nodes/-home-/abc/content")
    assert info.value.status == 302
    assert "cdn.test" in str(info.value), "die Umleitung gehoert in die Meldung"


async def test_eine_umleitung_wird_nicht_wiederholt():
    """Eine Umleitung ist eine Aussage, keine Stoerung."""
    versuche = []

    def handler(_request):
        versuche.append(1)
        return httpx.Response(301, headers={"Location": "https://anderswo.test/"})

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(EduSharingError):
            await t.request("GET", "/_about")
    assert len(versuche) == 1


async def test_eine_umleitung_ohne_location_wird_trotzdem_gemeldet():
    def handler(_request):
        return httpx.Response(304)

    async with _transport(handler) as t:
        with pytest.raises(EduSharingError):
            await t.request("GET", "/_about")


async def test_zweihundert_bleibt_erfolg():
    """Gegenprobe: die neue Grenze darf den Normalfall nicht treffen."""
    async with _transport(_ok) as t:
        assert (await t.request("GET", "/_about")).status_code == 200


# --- Parameter, die nichts taten (Audit A11, A14) -------------------------

async def test_ein_eigener_client_bringt_sein_eigenes_zeitlimit_mit():
    """``timeout`` wurde geprueft und dann verworfen, sobald ein Client
    uebergeben wurde -- gemessen: ``timeout=0.5`` ergab ``Timeout(5.0)``, die
    httpx-Vorgabe. Wer fuer einen latenzkritischen Pfad kurz stellt, bekam
    still die Vorgabe. Das Zeitlimit gehoert dem Client, also sagt es die
    Bibliothek, statt es anzunehmen."""
    eigener = httpx.AsyncClient(timeout=1.5)
    with pytest.raises(EduSharingError, match="timeout"):
        Transport(REPO, timeout=0.5, client=eigener)
    await eigener.aclose()


async def test_ein_eigener_client_ohne_zeitlimitangabe_ist_erlaubt():
    """Gegenprobe: nur die *widerspruechliche* Angabe wird abgelehnt."""
    eigener = httpx.AsyncClient(timeout=1.5)
    t = Transport(REPO, client=eigener)
    assert t._client.timeout.read == 1.5
    await eigener.aclose()


@pytest.mark.parametrize("wert", ["schnell", float("nan"), [1]])
def test_unbrauchbare_zahlenwerte_werden_als_bibliotheksfehler_abgelehnt(wert):
    """``at_least`` verglich blind. Ein Nicht-Zahlenwert gab einen TypeError
    statt eines EduSharingError -- die Bibliothek deckte ihre eigene Eingabe
    nicht mit ihrem eigenen Fehlertyp ab. Und ``nan`` kam durch, weil jeder
    Vergleich mit nan falsch ist; httpx bekam dann ein Zeitlimit, das nie
    ablaeuft."""
    with pytest.raises(EduSharingError):
        Transport(REPO, timeout=wert)


@pytest.mark.parametrize("wert", [None, "drei", float("nan")])
def test_unbrauchbare_wiederholungszahlen_ebenso(wert):
    """Dieselbe Pruefung, ein anderer Parameter -- ``max_retries`` hat keinen
    None-Sonderfall, hier bleibt None ein Fehler."""
    with pytest.raises(EduSharingError):
        Transport(REPO, max_retries=wert)


def test_timeout_none_heisst_vorgabe():
    """Die Gegenprobe zum neuen Sonderfall: ``None`` ist die Art zu sagen
    "nimm die Vorgabe", nicht ein unbrauchbarer Wert."""
    t = Transport(REPO, timeout=None)
    assert t._client.timeout.read == DEFAULT_TIMEOUT


async def test_verborgene_details_werden_nur_einmal_wiederholt():
    """Gemessen am 28.08.2026 gegen redaktion.openeduhub.net.

    Eine Instanz kann ihre Fehlermeldungen zurueckhalten
    (``security.logging.displayLevel``). Die 5xx-Einordnung liest genau diesen
    Text, also bleibt ein verkleidetes "nicht angemeldet" ein ServerError --
    und der wird wiederholt. Gemessen an derselben Adresse: **4 Anfragen gegen
    Produktiv, 1 gegen Staging**.

    Einordnen laesst sich das nicht; was der Server verschweigt, kann die
    Bibliothek nicht erraten. Die Wiederholung deckeln schon, und zwar nach dem
    Muster, das dieser Transport fuer den 401 unter Nebenlaeufigkeit bereits
    gewaehlt hat: einmal, nicht ``max_retries``-mal. Eine zusaetzliche Anfrage
    ist ein fairer Preis fuer einen moeglicherweise voruebergehenden Fehler;
    drei sind eine Strafe dafuer, dass die Instanz schweigt.
    """
    versuche = []

    def handler(_request):
        versuche.append(1)
        return httpx.Response(500, json={
            "error": "java.lang.Exception",
            "message": "Details hidden: You can configure the output via "
                       "security.logging.displayLevel",
        })

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(ServerError):
            await t.request("GET", "/_about")
    assert len(versuche) == 2, (
        f"erwartet ein Versuch plus eine Wiederholung, waren {len(versuche)}")


async def test_ein_gewoehnlicher_500_wird_weiter_voll_wiederholt():
    """Der Deckel gilt nur dort, wo die Meldung fehlt -- sonst waere er eine
    stille Verschlechterung der Fehlertoleranz fuer alle anderen."""
    versuche = []

    def handler(_request):
        versuche.append(1)
        return httpx.Response(500, json={"error": "java.lang.Exception",
                                         "message": "Something genuinely broke"})

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(ServerError):
            await t.request("GET", "/_about")
    assert len(versuche) == 4


# --- Streaming-Download mit Deckel (Audit SEC-2, 06.09.2026) ----------------
#
# request() liest jeden Koerper ganz in den Speicher, bevor jemand seine
# Groesse sehen kann. download() prueft die angekuendigte Groesse vor dem
# ersten Byte und zaehlt mit, waehrend sie ankommen.

async def _stueckweise(*teile: bytes):
    for teil in teile:
        yield teil


async def test_download_liest_den_koerper_stueckweise():
    def handler(request):
        return httpx.Response(200, content=_stueckweise(b"ab", b"cd", b"ef"))

    async with _transport(handler) as t:
        assert await t.download("/x") == b"abcdef"


async def test_download_bricht_ueber_max_bytes_ab():
    """Ohne Content-Length zaehlt der Transport mit und bricht ab, statt alles
    zu halten und dann zu messen."""
    def handler(request):
        return httpx.Response(200, content=_stueckweise(b"x" * 60, b"x" * 60))

    async with _transport(handler) as t:
        with pytest.raises(ContentTooLargeError):
            await t.download("/x", max_bytes=100)


async def test_download_lehnt_eine_angekuendigte_groesse_vor_dem_lesen_ab():
    """Review 06.09.2026 (F7): MockTransport reicht einen bytes-Koerper als ein
    Stueck durch, also bewies der Test nicht, dass vor dem ersten Byte
    abgelehnt wird. Jetzt merkt sich der Koerper, ob er gezogen wurde."""
    gezogen = []

    async def koerper():
        gezogen.append(1)
        yield b"x" * 1000

    def handler(request):
        return httpx.Response(200, content=koerper(), headers={"Content-Length": "1000"})

    async with _transport(handler) as t:
        with pytest.raises(ContentTooLargeError, match="1000"):
            await t.download("/x", max_bytes=100)
        assert gezogen == [], "kein Byte gelesen"
        assert len(await t.download("/x", max_bytes=1000)) == 1000
        assert len(await t.download("/x")) == 1000


async def test_download_wird_wie_ein_get_wiederholt():
    """Review 06.09.2026 (F2): die erste Fassung lief am Transport vorbei und
    verlor alle Wiederholungen -- ein 502, ein Verbindungsfehler oder der
    gemessene 401-Ausrutscher liessen jeden Datei-Fan-out scheitern, der
    zuvor durchkam. Ein Download ist ein GET und wird wie eines wiederholt."""
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) == 1:
            return httpx.Response(502, text="")
        if len(versuche) == 2:
            raise httpx.ConnectError("weg", request=request)
        return httpx.Response(200, content=b"Dateiinhalt")

    async with _transport(handler, max_retries=3) as t:
        assert await t.download("/x", max_bytes=100) == b"Dateiinhalt"
    assert len(versuche) == 3


async def test_zu_gross_wird_nicht_wiederholt():
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(200, content=b"x" * 200)

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(ContentTooLargeError):
            await t.download("/x", max_bytes=100)
    assert len(versuche) == 1


async def test_eine_fehlerseite_wird_begrenzt_gelesen():
    """Review 06.09.2026 (F10): max_bytes galt nicht fuer den Koerper eines
    5xx. Eine Fehlerseite wird bei 64 KiB abgeschnitten, nicht abgelehnt --
    der Fehler bleibt ein ServerError."""
    def handler(request):
        return httpx.Response(500, content=b"e" * 200_000)

    async with _transport(handler, max_retries=0) as t:
        with pytest.raises(ServerError) as fehler:
            await t.download("/x", max_bytes=10)
    assert len(str(fehler.value)) < 70_000


async def test_download_mit_eigener_anmeldung():
    """Review 06.09.2026 (F11): download() kennt credential= wie request()."""
    gesehen = []

    def handler(request):
        gesehen.append(request.headers.get("authorization"))
        return httpx.Response(200, content=b"x")

    async with _transport(handler) as t:
        await t.download("/x", credential=ANONYMOUS)
    assert gesehen == [None]


async def test_download_meldet_umleitung_status_und_netzfehler():
    """Dieselben Regeln wie request(): eine Umleitung ist kein Erfolg (Audit
    A8), ein Status ab 400 wird zum passenden Fehler, ein Netzfehler zum
    TransportError."""
    def handler(request):
        pfad = request.url.path
        if pfad.endswith("/kaputt"):
            raise httpx.ReadTimeout("zu langsam", request=request)
        if pfad.endswith("/weg"):
            return httpx.Response(302, headers={"location": "https://anderswo.test/"})
        return httpx.Response(404, json={"error": "DAOMissingException", "message": "nein"})

    async with _transport(handler) as t:
        with pytest.raises(EduSharingError, match="redirected"):
            await t.download("/weg")
        with pytest.raises(NotFoundError):
            await t.download("/fehlt")
        with pytest.raises(TransportError):
            await t.download("/kaputt")


async def test_download_traegt_die_anmeldung_nur_zum_repositorium():
    gesehen = {}

    def handler(request):
        gesehen[request.url.host] = request.headers.get("authorization")
        return httpx.Response(200, content=b"x")

    async with _transport(handler) as t:
        await t.download("/x")
        await t.download("https://fremd.example.test/datei")
    assert gesehen["repositorium.example.test"] is not None
    assert gesehen["fremd.example.test"] is None


async def test_vorenthaltener_5xx_bei_einem_post_nennt_den_verdacht():
    """Review 06.09.2026 (F4): auf der Produktivinstanz (Meldungen versteckt)
    kommt der gemessene 401-Ausrutscher als 500 "details hidden" an. Fuer ein
    POST wird er nicht wiederholt -- ob es lief, weiss niemand -- aber der
    Fehler sagt das, statt wie ein Serverfehler auszusehen."""
    versuche = []

    def handler(request):
        versuche.append(1)
        return httpx.Response(500, json={"error": "java.lang.Exception",
                                         "message": "details hidden"})

    async with _transport(handler, max_retries=2) as t:
        with pytest.raises(ServerError) as fehler:
            await t.request("POST", WRITE)
    assert len(versuche) == 1
    assert any("read back" in n for n in fehler.value.__notes__)


# --- ARC-2/API-2: der 429 ist eine Absage, kein Ergebnis --------------------


def _gewartet(monkeypatch) -> list[float]:
    """Zeichnet auf, was geschlafen worden waere, statt zu schlafen."""
    dauern: list[float] = []

    async def statt_schlaf(dauer):
        dauern.append(dauer)

    monkeypatch.setattr(asyncio, "sleep", statt_schlaf)
    return dauern


async def test_ein_429_kommt_als_rate_limited_error_mit_der_wartezeit():
    """Bisher fiel der 429 auf die Basisklasse: nicht zu unterscheiden, und
    die Zahl im Header las niemand (Audit API-2)."""
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "7"},
                              json={"message": "rate limit"})

    async with _transport(handler, max_retries=0) as t:
        with pytest.raises(RateLimitedError) as fehler:
            await t.request("GET", "/x")
    assert fehler.value.status == 429
    assert fehler.value.retry_after == 7.0


async def test_ein_429_auf_ein_post_wird_wiederholt():
    """Anders als ein 5xx sagt der 429, dass die Anfrage *nicht* ausgefuehrt
    wurde -- der Server hat sie abgewiesen. Also darf auch ein Schreibvorgang
    erneut gesendet werden, ohne dass er zweimal ankommt."""
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("POST", WRITE)
    assert len(versuche) == 2
    assert antwort.json() == {"ok": True}


async def test_die_genannte_wartezeit_wird_eingehalten(monkeypatch):
    """Frueher wiederzukommen, als der Dienst gesagt hat, ist genau das, was
    der 429 verhindern soll."""
    dauern = _gewartet(monkeypatch)
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) == 1:
            return httpx.Response(429, headers={"Retry-After": "12"})
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, max_retries=2, backoff_base=0.0) as t:
        await t.request("GET", "/x")
    assert dauern == [12.0]


async def test_eine_zu_lange_wartezeit_wird_dem_aufrufer_gegeben(monkeypatch):
    """Eine Stunde in einem Bibliotheksaufruf zu schlafen waere ein
    Aufhaenger. Der Fehler traegt die Zahl, der Aufrufer kann einplanen."""
    dauern = _gewartet(monkeypatch)

    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "3600"})

    async with _transport(handler, max_retries=3) as t:
        with pytest.raises(RateLimitedError) as fehler:
            await t.request("GET", "/x")
    assert dauern == []
    assert fehler.value.retry_after == 3600.0


async def test_der_backoff_streut(monkeypatch):
    """Ohne Jitter kaeme eine Fan-out-Welle geschlossen zurueck. Gestreut
    liegt die Wartezeit zwischen halbem und vollem Schritt (Audit ARC-2)."""
    dauern = _gewartet(monkeypatch)

    def handler(request):
        return httpx.Response(503)

    async with _transport(handler, max_retries=2, backoff_base=1.0) as t:
        with pytest.raises(ServerError):
            await t.request("GET", "/x")
    assert len(dauern) == 2
    assert 0.5 <= dauern[0] <= 1.0
    assert 1.0 <= dauern[1] <= 2.0


# --- Review 08.09.2026: Retry-After ist die Antwort auf den 429 -----------


async def test_ein_retry_after_bei_einem_5xx_aendert_die_kurve_nicht(monkeypatch):
    """RFC 9110 erlaubt ``Retry-After`` auch bei einem 503, aber diese
    Bibliothek hat das nie gemessen und nie dokumentiert.

    Beachtet machte es aus drei Pausen von 0,5 bis 2 s drei von je 30 s -- in
    einem Fan-out mit acht Wegen ein Vielfaches -- und aus einem langen Wert
    gar keine Wiederholung mehr. Der Fehler kam ausserdem als ``ServerError``
    an, sodass niemand, der auf ``RateLimitedError`` prueft, die Zahl je zu
    sehen bekam (Review 08.09.2026)."""
    dauern = _gewartet(monkeypatch)

    def handler(request):
        return httpx.Response(503, headers={"Retry-After": "30"})

    async with _transport(handler, max_retries=2, backoff_base=1.0) as t:
        with pytest.raises(ServerError) as fehler:
            await t.request("GET", "/x")
    assert len(dauern) == 2, "beide Wiederholungen finden statt"
    assert all(d <= 2.0 for d in dauern), f"die eigene Kurve, nicht 30 s: {dauern}"
    assert fehler.value.retry_after is None


async def test_eine_lange_wartezeit_bei_einem_5xx_kostet_keine_wiederholung(monkeypatch):
    """Die andere Haelfte desselben Befunds: ein Proxy, der bei Wartung
    ``Retry-After: 3600`` mitschickt, nahm dem Transport alle Versuche."""
    dauern = _gewartet(monkeypatch)
    versuche = []

    def handler(request):
        versuche.append(1)
        if len(versuche) == 1:
            return httpx.Response(503, headers={"Retry-After": "3600"})
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, max_retries=2) as t:
        antwort = await t.request("GET", "/x")
    assert len(versuche) == 2
    assert antwort.json() == {"ok": True}
    assert len(dauern) == 1


# --- SEC-4: ein folgender Client hebelt die 3xx-Wache aus -----------------


def test_ein_client_der_umleitungen_folgt_wird_abgelehnt():
    """httpx behaelt eigene Kopfzeilen ueber Ursprungsgrenzen hinweg. Ein
    Client mit ``follow_redirects=True`` traegt damit den Anmeldekopf dorthin,
    wohin ein Gateway zeigt -- gemessen: die zweite Anfrage an einen anderen
    Host hatte den Schluessel noch (Audit SEC-4). Und jede der vier Wachen
    gegen 3xx laeuft nie, wenn der Client die Umleitung schon genommen hat."""
    with pytest.raises(EduSharingError, match="follow_redirects"):
        Transport(REPO, client=httpx.AsyncClient(follow_redirects=True))


def test_ein_client_ohne_umleitungen_geht_durch():
    """Die Gegenprobe: die Vorgabe von httpx ist False, und die ist richtig."""
    t = Transport(REPO, client=httpx.AsyncClient())
    assert t._client.follow_redirects is False


# --- API-1: eine Antwort, die kein JSON ist, bleibt im Vertrag ------------


async def test_ein_html_koerper_wird_zu_einem_servererror():
    """Ein Reverse-Proxy, der eine Loginseite mit 200 ausliefert, brachte
    ``json.JSONDecodeError`` aus der Standardbibliothek zurueck -- eine
    Ausnahme, die ausserhalb von ``EduSharingError`` steht und die
    ``agent.result.as_result`` nicht faengt (Audit API-1)."""
    def handler(request):
        return httpx.Response(200, text="<html><body>Bitte anmelden</body></html>")

    async with _transport(handler) as t:
        with pytest.raises(ServerError, match="non-JSON"):
            await t.json("GET", "/x")


# --- F01 (Fremdpruefung 09.09.2026): eine Sitzung ist keine Identitaet -----
#
# ``auth.py`` beginnt mit dem Satz, um den es hier geht: "Credentials are
# values, not global state. Every request gets its own. A service that serves
# many people -- an MCP server, say -- cannot otherwise keep straight who is
# asking."
#
# Der Cookie-Speicher des geteilten ``httpx.AsyncClient`` hob das auf. Gemessen
# am 09.09.2026: nach einer Antwort mit ``Set-Cookie`` trugen die naechste
# **anonyme** und die naechste Anfrage einer **anderen** Anmeldung Alices
# ``JSESSIONID`` mit. Auf HTTP-Ebene war die ausdruecklich anonyme Anfrage
# weiter mit Alices Sitzung verbunden.


def _setzt_sitzung(name: str):
    """Ein Handler, der wie edu-sharing eine Sitzung eroeffnet."""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True},
            headers={"set-cookie": f"JSESSIONID={name}; Path=/edu-sharing"})
    return handler


async def test_eine_fremde_sitzung_geht_nicht_mit():
    """Alice, dann anonym, dann Bob -- niemand traegt Alices Sitzung."""
    gesehen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append((request.headers.get("authorization", ""),
                        request.headers.get("cookie", "")))
        return _setzt_sitzung("alice-session")(request)

    async with _transport(handler) as transport:
        await transport.request("GET", "/node/v1/nodes/-home-/n1")
        await transport.request("GET", "/node/v1/nodes/-home-/n1",
                                credential=ANONYMOUS)
        await transport.request("GET", "/node/v1/nodes/-home-/n1",
                                credential=("bob", "geheim"))

    anmeldungen = [a for a, _ in gesehen]
    assert anmeldungen[1] == "", "die anonyme Anfrage traegt keine Anmeldung"
    assert anmeldungen[2] not in ("", anmeldungen[0]), "Bob ist nicht Alice"
    assert [c for _, c in gesehen] == ["", "", ""], (
        "eine Antwort hat eine Sitzung eroeffnet und die naechsten Anfragen "
        "haben sie mitgetragen")


async def test_auch_gleichzeitig_traegt_niemand_die_sitzung_eines_anderen():
    """Der Fall, den ein Dienst mit vielen Nutzern wirklich hat.

    Ein Speicher, der zwischen den Anfragen geleert wuerde, waere hier wieder
    fehleranfaellig -- darum wird gar nicht erst gespeichert.
    """
    gesehen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(request.headers.get("cookie", ""))
        await asyncio.sleep(0)
        return _setzt_sitzung("wer-auch-immer")(request)

    async with _transport(handler, max_concurrency=8) as transport:
        # Erst eine Anfrage allein: sie eroeffnet die Sitzung. Ohne sie waere
        # der Speicher leer, waehrend die acht gebaut werden, und dieser Test
        # gruen, ohne etwas zu pruefen.
        await transport.request("GET", "/node/v1/nodes/-home-/n0")
        await asyncio.gather(*(
            transport.request("GET", f"/node/v1/nodes/-home-/n{i}",
                              credential=(f"nutzer{i}", "geheim"))
            for i in range(8)))

    assert gesehen == [""] * 9, gesehen


async def test_eine_sitzung_als_anmeldung_geht_sehr_wohl_mit():
    """Der Erweiterungspunkt bleibt: ``Credential`` ist das Protokoll, und ein
    Cookie, das mitgehen **soll**, kommt als eins herein.

    Ohne diesen Test waere die Wache darueber gruen, dass Cookies gar nicht
    mehr funktionieren -- was etwas anderes ist als "sie tragen keine fremde
    Identitaet".
    """
    class Sitzung:
        is_anonymous = False

        def headers(self) -> dict[str, str]:
            return {"Cookie": "JSESSIONID=meine-eigene"}

    gesehen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append(request.headers.get("cookie", ""))
        return httpx.Response(200, json={"ok": True})

    async with _transport(handler, credential=Sitzung()) as transport:
        await transport.request("GET", "/node/v1/nodes/-home-/n1")

    assert gesehen == ["JSESSIONID=meine-eigene"]


# --- F02 (Fremdpruefung 09.09.2026): fremde Zugangsdaten am eigenen Client --
#
# ``is_repository_url(url)`` steht in REFERENCE als "whether credentials would
# be attached". Mit einem eingebrachten Client, der Zugangsdaten als Vorgabe
# traegt, ist diese Auskunft unwahr: httpx ergaenzt sie unabhaengig davon, wo
# die Anfrage hingeht. Gemessen am 09.09.2026 landeten ``Authorization: Basic
# TEST_ONLY`` und ``X-API-Key: DUMMY_KEY`` an ``cdn.example.test``.
#
# Gefiltert wird nicht: fremde Kopfzeilennamen lassen sich nicht aufzaehlen,
# und ein Filter waere eine Zusage, die er nicht halten kann. Abgelehnt wird,
# was httpx nicht selbst setzt -- gemessen sind das ``accept``,
# ``accept-encoding``, ``connection`` und ``user-agent``.


@pytest.mark.parametrize("bauen", [
    lambda: httpx.AsyncClient(headers={"Authorization": "Basic TEST_ONLY"}),
    lambda: httpx.AsyncClient(headers={"X-API-Key": "DUMMY_KEY"}),
    lambda: httpx.AsyncClient(headers={"Cookie": "JSESSIONID=fremd"}),
    lambda: httpx.AsyncClient(auth=("nutzer", "DUMMY_PASSWORD")),
])
def test_ein_client_mit_eigenen_zugangsdaten_wird_abgelehnt(bauen):
    """Sonst gehen sie an jedes Ziel mit, auch an ein externes."""
    with pytest.raises(EduSharingError) as fehler:
        Transport(REPO, client=bauen())
    assert "credential" in str(fehler.value).lower()


def test_die_meldung_wiederholt_den_wert_nicht():
    """Eine Fehlermeldung wird protokolliert. Der Name der Kopfzeile erklaert
    das Problem, ihr Wert ist das Geheimnis."""
    with pytest.raises(EduSharingError) as fehler:
        Transport(REPO, client=httpx.AsyncClient(
            headers={"X-API-Key": "DUMMY_KEY"}))
    assert "DUMMY_KEY" not in str(fehler.value)
    assert "x-api-key" in str(fehler.value).lower()


async def test_ein_client_darf_seine_eigenen_vorgaben_ueberschreiben():
    """Die Gegenprobe. httpx setzt vier Kopfzeilen selbst; sie anders zu
    belegen ist keine Anmeldung, und ein Client ohne Vorgaben erst recht
    nicht. Ohne diesen Test waere die Regel gruen, wenn sie jeden Client
    ablehnt."""
    async with httpx.AsyncClient(headers={"User-Agent": "meins/1.0"}) as c:
        Transport(REPO, client=c)
    async with httpx.AsyncClient() as c:
        Transport(REPO, client=c)


async def test_ein_externer_download_traegt_die_anmeldung_des_repositoriums_nicht():
    """Was die Regel schuetzt, am Verhalten statt an der Ablehnung.

    ``download_url`` eines Datensatzes kann auf einen anderen Host zeigen; die
    eigene Anmeldung geht dorthin nicht mit. Die Wache gab es fuer die
    Bibliothekskopfzeilen schon -- hier steht sie neben der Regel, die die
    zweite Quelle schliesst.
    """
    gesehen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        gesehen.append((request.url.host or "",
                        request.headers.get("authorization", ""),
                        request.headers.get("cookie", "")))
        return httpx.Response(200, content=b"daten")

    async with _transport(handler) as transport:
        await transport.download("https://cdn.example.test/datei")

    assert gesehen == [("cdn.example.test", "", "")]


# --- F05 (Fremdpruefung 09.09.2026): Kodierung genau einmal ----------------
#
# Mit ``max_bytes`` liest ``_send`` den Koerper stueckweise -- und
# ``aiter_bytes()`` liefert bereits **entpackte** Bytes. Aus ihnen wurde dann
# eine neue Antwort gebaut, mit den urspruenglichen Kopfzeilen und damit auch
# mit ``Content-Encoding: gzip``. Die neue Antwort entpackte ein zweites Mal.
#
# Gemessen am 09.09.2026: derselbe gzip-Strom lud ohne Grenze richtig, mit
# ``max_bytes=1000`` ergab er ``TransportError: DecodingError ... incorrect
# header check`` -- bei einem Inhalt weit unter der Grenze. Deterministisch,
# also half auch keine Wiederholung.

TEXT = b"# Ein kleiner Skill\n\nNur ein paar Zeilen.\n"


def _gzip_handler(inhalt: bytes = TEXT, *, status: int = 200):
    gepackt = gzip.compress(inhalt)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, content=gepackt,
            headers={"content-encoding": "gzip",
                     "content-length": str(len(gepackt))})
    return handler


@pytest.mark.parametrize("grenze", [None, 1000])
@pytest.mark.parametrize("gepackt", [False, True])
async def test_derselbe_text_kommt_gepackt_wie_ungepackt_an(gepackt, grenze):
    """Vier Faelle, ein Ergebnis. Das ist der ganze Befund."""
    handler = _gzip_handler() if gepackt else (
        lambda _r: httpx.Response(200, content=TEXT))
    async with _transport(handler) as transport:
        assert await transport.download("/skill.md", max_bytes=grenze) == TEXT


async def test_die_kopfzeilen_beschreiben_den_koerper_der_ankommt():
    """Die Ursache, nicht nur ihre Wirkung: eine Antwort, deren Koerper
    entpackt ist, darf sich nicht als gepackt ausgeben -- und ihre Laenge ist
    die des entpackten."""
    async with _transport(_gzip_handler()) as transport:
        antwort = await transport.request("GET", "/skill.md", max_bytes=1000)
    assert "content-encoding" not in antwort.headers
    assert antwort.headers["content-length"] == str(len(TEXT))


async def test_die_groessengrenze_gilt_weiterhin_dem_entpackten_inhalt():
    """Die Gegenprobe, ohne die der Fix den Schutz mitnehmen koennte: die
    komprimierte Groesse liegt unter der Grenze, die entpackte darueber."""
    gross = b"x" * 100_000
    async with _transport(_gzip_handler(gross)) as transport:
        with pytest.raises(ContentTooLargeError):
            await transport.download("/gross.bin", max_bytes=1000)
    assert len(gzip.compress(gross)) < 1000


async def test_eine_angekuendigte_gepackte_groesse_lehnt_nicht_vorschnell_ab():
    """Die angekuendigte Laenge ist die der **gepackten** Bytes; die Grenze
    meint die entpackten. Sie gegeneinander zu halten lehnt einen Inhalt ab,
    der hineinpasst.

    Unkomprimierbare Daten, damit der Fall ueberhaupt eintritt: gepackt sind
    es 1023 Bytes, entpackt 1000, die Grenze liegt bei 1010. Mit gut
    komprimierbaren Daten -- ``b"y" * 4000`` -- laege die angekuendigte Laenge
    weit unter jeder Grenze, und dieser Test waere gruen, ohne die Regel je zu
    beruehren. Genau so stand er zuerst da.
    """
    zufall = random.Random(7)
    inhalt = bytes(zufall.randrange(256) for _ in range(1000))
    assert len(gzip.compress(inhalt)) > 1010, "sonst prueft der Test nichts"
    async with _transport(_gzip_handler(inhalt)) as transport:
        assert await transport.download("/klein.bin", max_bytes=1010) == inhalt


async def test_eine_gepackte_fehlerantwort_bleibt_lesbar():
    """Auch der Fehlerweg liest stueckweise, also entpackt auch er.

    Geprueft am **Text der Meldung**: nur ein genau einmal entpackter Koerper
    laesst sich als JSON lesen, und nur dann steht die Ursache im Fehler
    statt eines nackten "HTTP 500". Vorher endete dieser Weg im
    ``DecodingError`` -- also gar nicht als ``ServerError``.
    """
    koerper = json.dumps({"error": "org.edu_sharing.DAOException",
                          "message": "kaputt"}).encode()
    async with _transport(_gzip_handler(koerper, status=500), max_retries=0) as t:
        with pytest.raises(ServerError) as fehler:
            await t.download("/skill.md", max_bytes=1000)
    assert "kaputt" in str(fehler.value)
    assert "DAOException" in str(fehler.value)


# --- F14 (Fremdpruefung 09.09.2026): eine Grenze, die nicht begrenzt -------
#
# ``at_least`` prueft Zahl, Endlichkeit und Untergrenze. Fuer Sekunden ist das
# richtig; fuer eine Semaphore nicht. ``asyncio.Semaphore(1.5)`` zaehlt 1.5,
# 0.5, -0.5 und erreicht die Null nie, an der sie blockieren wuerde.
#
# Gemessen am 09.09.2026: ein Transport mit ``max_concurrency=1.5`` liess zehn
# gleichzeitig gestartete Anfragen alle zugleich laufen.


@pytest.mark.parametrize("wert", [1.5, 2.0, "2", None])
def test_eine_gebrochene_parallelitaetsgrenze_wird_abgelehnt(wert):
    """``2.0`` ist dabei: es *ist* ganzzahlig, aber es ist keine ganze Zahl,
    und eine Konfiguration, die aus JSON kommt, liefert genau solche Werte.
    Die Regel bleibt einfacher, wenn sie keine Ausnahme hat."""
    with pytest.raises(EduSharingError):
        Transport(REPO, max_concurrency=wert)


@pytest.mark.parametrize("wert", [1.5, "3"])
def test_eine_gebrochene_wiederholungszahl_ebenso(wert):
    with pytest.raises(EduSharingError):
        Transport(REPO, max_retries=wert)


def test_die_stetigen_groessen_duerfen_weiterhin_bruchzahlen_sein():
    """Die Gegenprobe. Sekunden sind keine Anzahl -- eine Regel, die
    ``timeout=0.5`` ablehnt, waere die falsche Regel am falschen Parameter."""
    t = Transport(REPO, timeout=0.5, backoff_base=0.25)
    assert t.backoff_base == 0.25


async def test_eine_ganzzahlige_grenze_haelt_bei_parallelen_anfragen():
    """Und das Verhalten selbst, nicht nur die Ablehnung."""
    gleichzeitig = 0
    hoechststand = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal gleichzeitig, hoechststand
        gleichzeitig += 1
        hoechststand = max(hoechststand, gleichzeitig)
        await asyncio.sleep(0.01)
        gleichzeitig -= 1
        return httpx.Response(200, json={})

    async with _transport(handler, max_concurrency=2) as transport:
        await asyncio.gather(*(
            transport.request("GET", f"/node/v1/nodes/-home-/n{i}")
            for i in range(10)))
    assert hoechststand == 2


# --- R01 (Zweitpruefung 09.09.2026): ein schon gefuellter Speicher ---------
#
# Die Politik aus F01 verhindert das **Speichern** neuer Cookies. Einen bereits
# gefuellten Speicher leert sie nicht -- und httpx kopiert ihn beim Bauen der
# Anfrage in einen neuen Speicher, der die Politik nicht mitbekommt.
#
# Gemessen am 09.09.2026: ``AsyncClient(cookies={"JSESSIONID": ...})`` wurde
# angenommen, das Cookie ging an die ausdruecklich **anonyme** Anfrage und --
# ohne Domain-Bindung -- auch an ``cdn.example.test``.
#
# Dieselbe Entscheidung wie bei F02: ablehnen, nicht filtern. Pro Anfrage am
# gemeinsamen Speicher zu loeschen waere unter Parallelitaet keine Loesung.


@pytest.mark.parametrize("cookies", [
    {"JSESSIONID": "preexisting-dummy"},
    [("JSESSIONID", "preexisting-dummy")],
])
def test_ein_client_mit_vorhandenen_cookies_wird_abgelehnt(cookies):
    with pytest.raises(EduSharingError) as fehler:
        Transport(REPO, client=httpx.AsyncClient(cookies=cookies))
    assert "cookie" in str(fehler.value).lower()


def test_die_meldung_nennt_den_wert_des_cookies_nicht():
    """Ein Sitzungscookie ist ein Geheimnis wie ein Passwort."""
    with pytest.raises(EduSharingError) as fehler:
        Transport(REPO, client=httpx.AsyncClient(
            cookies={"JSESSIONID": "preexisting-dummy"}))
    assert "preexisting-dummy" not in str(fehler.value)


async def test_ein_client_mit_leerem_speicher_geht_weiterhin_durch():
    """Die Gegenprobe. Ohne sie waere die Regel gruen, wenn sie jeden Client
    ablehnt -- und die ganze Testsuite bringt Clients ein."""
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok)) as client:
        transport = Transport(REPO, client=client)
        await transport.request("GET", "/node/v1/nodes/-home-/n1")


async def test_eine_domaingebundene_sitzung_geht_ebenso_wenig_mit():
    """Auch ein korrekt auf das Repositorium beschraenktes Cookie bleibt eine
    fremde Anmeldung -- der Bericht misst, dass es die anonyme Anfrage
    weiterhin traegt."""
    speicher = httpx.Cookies()
    speicher.set("JSESSIONID", "dummy", domain="repositorium.example.test",
                 path="/edu-sharing")
    with pytest.raises(EduSharingError):
        Transport(REPO, client=httpx.AsyncClient(cookies=speicher))


async def test_ein_proxy_mit_fehlerobjekt_bleibt_im_vertrag():
    """Audit COR-23-1, der Weg, auf dem es gemessen wurde: ein 502 mit
    ``{"error": {...}}`` von einem Gateway vor dem Repositorium ergab einen
    ``builtins.AttributeError`` aus ``request`` -- ohne Wiederholung, ohne
    Status, und ``as_result`` reicht ihn durch."""
    def proxy(_request):
        return httpx.Response(502, json={"error": {"code": 502, "message": "Bad gateway"}})

    with pytest.raises(ServerError) as fehler:
        await _transport(proxy, max_retries=0).request("GET", "/_about")
    assert fehler.value.status == 502
    assert "Bad gateway" in str(fehler.value), "die Meldung des Proxys geht nicht verloren"
