"""Der Textextraktionsdienst: der Volltext hinter einer verlinkten Adresse.

Kein Teil des Repositoriums, sondern ein zweiter Dienst daneben -- wie die
b-api. Am 28.08.2026 gegen
``https://text-extraction.staging.openeduhub.net`` vermessen (FastAPI,
Version ``c766f2e5``):

* Drei Routen: ``/_ping``, ``/from-url``, ``/metrics``.
* ``POST /from-url`` nimmt ``{url*, method, browser_location, lang,
  output_format, preference}``. Vorgaben des Dienstes: ``method="simple"``,
  ``lang="auto"``, ``output_format="txt"``, ``preference="none"``.
* Antwort 200: ``{text, lang, status, version}``. ``status`` ist der
  HTTP-Status der **Zielseite**, nicht der des Dienstes.
* **424 statt 400.** Unbrauchbare Adresse, Seite ohne Text, privater Host --
  alles endet in ``424`` mit ``{"detail": {...}}``. Ein fehlendes Pflichtfeld
  ergibt ``422``.
* Eine edu-sharing-Download-URL ergibt ``424``: der Dienst kann nicht lesen,
  was das Repositorium selbst hostet.

Die Schutzpruefungen laufen, **bevor** irgendetwas gesendet wird. Eine Pruefung,
die richtig antwortet, nachdem der Dienst die Anfrage schon gestellt hat, hat
nichts geschuetzt.
"""

import asyncio
import json

import httpx
import pytest

from edusharing.errors import EduSharingError, RateLimitedError, ServerError
from edusharing.extraction import ExtractedText, TextExtraction

BASE = "https://text-extraction.test"


def _antwort(text: str = "Der Text.", *, lang: str = "de",
             status: int = 200) -> dict:
    return {"text": text, "lang": lang, "status": status, "version": "abc123"}


class Dienst:
    """Ein Extraktionsdienst, der sich merkt, was er bekommen hat."""

    def __init__(self, *, status: int = 200, body: dict | None = None) -> None:
        self.status = status
        self.body = body if body is not None else _antwort()
        self.anfragen: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/_ping"):
            return httpx.Response(200, json={"status": "ok", "version": "abc123"})
        self.anfragen.append(json.loads(request.content))
        return httpx.Response(self.status, json=self.body)

    def client(self, **kwargs) -> TextExtraction:
        kwargs.setdefault("backoff_base", 0.0)
        return TextExtraction(
            BASE,
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)),
            **kwargs,
        )


def _oeffentlich(_host: str) -> list[str]:
    """Aufloesung, die immer auf eine oeffentliche Adresse zeigt."""
    return ["93.184.216.34"]


def _privat(_host: str) -> list[str]:
    return ["10.1.2.3"]


def _kaputt(_host: str) -> list[str]:
    raise OSError("Name or service not known")


# --- Schutz, bevor gesendet wird -------------------------------------------

@pytest.mark.parametrize("url, grund", [
    ("ftp://example.org/datei.txt", "not_http"),
    ("file:///etc/passwd", "not_http"),
    ("keine-url", "not_http"),
    ("", "not_http"),
    ("http://127.0.0.1/seite", "private_host"),
    ("http://10.1.2.3/", "private_host"),
    ("http://192.168.0.7/", "private_host"),
    ("http://169.254.169.254/latest/meta-data/", "private_host"),
    ("http://[::1]/", "private_host"),
    # Audit A6: NAT64 kam durch, weil `not is_global` es fuer oeffentlich
    # haelt -- die Aufzaehlung in agent/safety.py fing es. Seit beide
    # Regelsaetze gelten, faengt es auch dieser Weg.
    ("http://[64:ff9b::1]/", "private_host"),
    # Audit A7: andere Schreibweisen derselben Adresse.
    ("http://2130706433/", "private_host"),
    ("http://0x7f000001/", "private_host"),
])
async def test_schutz_verweigert_ohne_zu_senden(url, grund):
    """Der Wolkendienst-Metadatenendpunkt (169.254.169.254) steht mit in der
    Liste: er ist die klassische Beute einer SSRF."""
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of(url)
    assert ergebnis.reason == grund
    assert ergebnis.text == ""
    assert dienst.anfragen == [], "es wurde trotz Verweigerung gesendet"


async def test_schutz_prueft_auch_die_aufloesung():
    """Ein Name, der auf eine private Adresse zeigt, ist derselbe Angriff mit
    einem Umweg."""
    dienst = Dienst()
    async with dienst.client(resolve=_privat) as client:
        ergebnis = await client.text_of("https://sieht-harmlos-aus.test/")
    assert ergebnis.reason == "private_host"
    assert dienst.anfragen == []


async def test_unaufloesbarer_name_wird_verweigert():
    """Verweigert statt durchgewunken: der Dienst loest womoeglich auf, was wir
    nicht konnten -- und dann haette die Pruefung nichts geprueft."""
    dienst = Dienst()
    async with dienst.client(resolve=_kaputt) as client:
        ergebnis = await client.text_of("https://gibtesnicht.test/")
    assert ergebnis.reason == "dns_failed"
    assert dienst.anfragen == []


async def test_die_url_landet_nicht_im_log(caplog):
    """Eine vom Aufrufer gewaehlte URL kann ein Token im Query tragen. Eine
    Verweigerung darf nicht das sein, was es protokolliert."""
    dienst = Dienst()
    with caplog.at_level("DEBUG", logger="edusharing.extraction"):
        async with dienst.client(resolve=_privat) as client:
            await client.text_of("https://intern.test/pfad?token=streng-geheim")
    text = caplog.text
    assert "streng-geheim" not in text
    assert "intern.test" in text, "der Host gehoert ins Log, damit es nutzt"


async def test_unsafe_url_does_not_log_secrets_from_the_path_or_query(caplog):
    dienst = Dienst()
    url = "https://example.test/PATH_SECRET/file\\name?token=QUERY_SECRET"
    with caplog.at_level("WARNING", logger="edusharing.extraction"):
        async with dienst.client(resolve=_oeffentlich) as client:
            assert (await client.text_of(url)).reason == "unsafe_url"
    assert dienst.anfragen == []
    assert "unsafe" in caplog.text
    assert "PATH_SECRET" not in caplog.text
    assert "QUERY_SECRET" not in caplog.text


# --- Der gute Fall ---------------------------------------------------------

async def test_text_kommt_zurueck():
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/seite")
    assert isinstance(ergebnis, ExtractedText)
    assert ergebnis.text == "Der Text."
    assert ergebnis.lang == "de"
    assert ergebnis.status == 200
    assert ergebnis.reason == ""
    assert ergebnis.truncated is False
    assert ergebnis.char_count == len("Der Text.")


async def test_der_koerper_traegt_die_gemessenen_felder():
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        await client.text_of("https://example.org/seite", method="browser",
                             output_format="markdown", lang="de")
    gesendet = dienst.anfragen[0]
    assert gesendet == {
        "url": "https://example.org/seite",
        "method": "browser",
        "output_format": "markdown",
        "lang": "de",
        "preference": "none",
    }


async def test_gemeldet_wird_was_gesendet_wurde():
    """Sonst nennt die Antwort eine Adresse, die nie abgerufen wurde.

    Der Fall, der das gefaehrlich macht, hat das MCP am 03.08.2026 gemessen:
    eine als URL deklarierte Zeichenkette darf einen Zeilenumbruch enthalten,
    und die Adresszerlegung entfernt ihn. Wer die Roheingabe ausgibt, faelscht
    in einer Herkunftszeile eine zweite.
    """
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/se\nite")
    assert ergebnis.url == dienst.anfragen[0]["url"]
    assert "\n" not in ergebnis.url
    assert ergebnis.url == "https://example.org/seite"


async def test_unbekannte_methode_wird_abgelehnt():
    """Der Dienst kennt genau zwei. Ein Tippfehler soll hier auffallen und
    nicht als 422 aus der Ferne zurueckkommen."""
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        with pytest.raises(ValueError, match="browser"):
            await client.text_of("https://example.org/", method="playwright")
    assert dienst.anfragen == []


# --- Kuerzen ---------------------------------------------------------------

async def test_kuerzen_meldet_die_volle_laenge():
    dienst = Dienst(body=_antwort("ein zwei drei vier fuenf sechs"))
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/", max_chars=12)
    assert ergebnis.truncated is True
    assert ergebnis.char_count == len("ein zwei drei vier fuenf sechs")
    assert ergebnis.text == "ein zwei", "an der Wortgrenze, nicht mitten im Wort"


async def test_kuerzen_ohne_wortgrenze_schneidet_hart():
    dienst = Dienst(body=_antwort("abcdefghijklmnop"))
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/", max_chars=5)
    assert ergebnis.text == "abcde"
    assert ergebnis.truncated is True


async def test_kurzer_text_wird_nicht_gekuerzt():
    dienst = Dienst(body=_antwort("kurz"))
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/", max_chars=100)
    assert ergebnis.text == "kurz"
    assert ergebnis.truncated is False


async def test_unsinniges_max_chars_wird_abgelehnt():
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        with pytest.raises(ValueError):
            await client.text_of("https://example.org/", max_chars=0)


# --- Wenn der Dienst nichts findet -----------------------------------------

async def test_424_ist_kein_fehler_sondern_ein_grund():
    """Gemessen: eine Seite ohne Text, eine unbrauchbare Adresse und ein
    privater Host enden alle in 424. Kein Text ist ein normales Ergebnis."""
    dienst = Dienst(status=424, body={"detail": {
        "error_message": "No content was extracted.",
        "status": 404, "reason": "Not Found", "version": "abc123"}})
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/weg")
    assert ergebnis.reason == "no_text"
    assert ergebnis.text == ""
    assert ergebnis.status == 404, "der Status der Zielseite, nicht der 424"
    assert "No content" in ergebnis.detail


async def test_424_ohne_verwertbaren_koerper():
    dienst = Dienst(status=424, body={"detail": "irgendein String"})
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/weg")
    assert ergebnis.reason == "no_text"
    assert ergebnis.status == 0, "die Zielseite hat gar keinen Status gemeldet"


async def test_leerer_text_zaehlt_als_kein_text():
    dienst = Dienst(body=_antwort("   "))
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.org/")
    assert ergebnis.reason == "no_text"


# --- Wenn der Dienst selbst nicht mitspielt --------------------------------

async def test_422_ist_ein_fehler_dieser_bibliothek():
    """422 heisst: der Koerper war falsch. Das ist keine Aussage ueber die
    Zielseite und darf nicht als "kein Text" durchgehen."""
    dienst = Dienst(status=422, body={"detail": [{"msg": "Field required"}]})
    async with dienst.client(resolve=_oeffentlich) as client:
        with pytest.raises(EduSharingError, match="422"):
            await client.text_of("https://example.org/")


async def test_serverfehler_wird_wiederholt_und_dann_gemeldet():
    dienst = Dienst(status=503, body={"detail": "weg"})
    async with dienst.client(resolve=_oeffentlich, max_retries=2) as client:
        with pytest.raises(EduSharingError):
            await client.text_of("https://example.org/")
    assert len(dienst.anfragen) == 3, "ein Versuch plus zwei Wiederholungen"


async def test_ping_beantwortet_ob_der_dienst_da_ist():
    dienst = Dienst()
    async with dienst.client(resolve=_oeffentlich) as client:
        zustand = await client.ping()
    assert zustand["status"] == "ok"


# --- Konfiguration ---------------------------------------------------------

def test_ohne_umgebungsvariable_gibt_es_keinen_client(monkeypatch):
    """Kein Default, mit Absicht: das MCP hatte einen auf den Staging-Dienst
    und schickte damit Produktions-Material-URLs in eine fremde Umgebung."""
    monkeypatch.delenv(TextExtraction.ENV_BASE_URL, raising=False)
    with pytest.raises(EduSharingError, match=TextExtraction.ENV_BASE_URL):
        TextExtraction.from_env()


def test_mit_umgebungsvariable_entsteht_einer(monkeypatch):
    monkeypatch.setenv(TextExtraction.ENV_BASE_URL, "https://extraktion.test/")
    client = TextExtraction.from_env()
    assert client.base_url == "https://extraktion.test"


@pytest.mark.parametrize("wert", [
    "extraktion.test",
    "ftp://extraktion.test",
    "https://extraktion.test/pfad?a=1",
    "https://alice:geheim@extraktion.test",           # SEC-1: Zugangsdaten
    "alice:geheim@extraktion.test",                   # ... auch ohne Schema
    "   ",
])
def test_unbrauchbare_basis_url_wird_abgelehnt(wert):
    """Ein Tippfehler darf keine Material-URLs an einen nicht gewaehlten Host
    schicken."""
    with pytest.raises(EduSharingError):
        TextExtraction(wert)


@pytest.mark.parametrize("wert", [
    "https://alice:geheim@extraktion.test",
    "https:/alice:geheim@extraktion.test",
    "alice:geheim@extraktion.test",
])
def test_zugangsdaten_stehen_nicht_in_der_meldung(wert):
    """Review 06.09.2026 (F8): die Ablehnung war getestet, die Maskierung
    nicht -- und "https:/user:pw@host" lief bis zur Schema-Pruefung, deren
    Meldung die Adresse samt Passwort wiederholte."""
    with pytest.raises(EduSharingError) as fehler:
        TextExtraction(wert)
    assert "geheim" not in str(fehler.value)


def test_repr_nennt_den_dienst():
    assert "extraktion.test" in repr(TextExtraction("https://extraktion.test"))


# --- Die Wege, die kein Test injiziert -------------------------------------

async def test_ohne_injektion_wird_wirklich_aufgeloest():
    """Deckt den echten Aufloeser ab, ohne ins Netz zu gehen.

    ``localhost`` ist keine IP-Literal-Adresse, faellt also nicht schon durch
    die erste Pruefung -- der Resolver muss laufen, und was er liefert, ist
    127.0.0.1.
    """
    dienst = Dienst()
    async with dienst.client() as client:
        ergebnis = await client.text_of("http://localhost/seite")
    assert ergebnis.reason == "private_host"
    assert dienst.anfragen == []


async def test_verbindungsfehler_wird_gemeldet():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz", request=request)

    client = TextExtraction(
        BASE, backoff_base=0.0, max_retries=1, resolve=_oeffentlich,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with client:
        with pytest.raises(EduSharingError, match="ConnectError"):
            await client.text_of("https://example.org/")


def test_repr_des_ergebnisses_nennt_den_kern():
    mit = ExtractedText(url="https://example.org/", text="abc", lang="de",
                        status=200, char_count=3, truncated=False)
    ohne = ExtractedText(url="https://example.org/", text="", lang="",
                         status=0, char_count=0, truncated=False,
                         reason="private_host")
    assert "3 chars" in repr(mit)
    assert "private_host" in repr(ohne)


# --- ARC-2/API-2: dieselbe Regel wie im Transport ---------------------------


def _mit_429(retry_after: str) -> TextExtraction:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": retry_after},
                              text="zu viele Anfragen")

    return TextExtraction(
        BASE, backoff_base=0.0, max_retries=2, resolve=_oeffentlich,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_ein_429_kommt_auch_hier_als_rate_limited_error(monkeypatch):
    """Der Dienst nennt eine Wartezeit; bis zum Audit las sie niemand, und der
    Fehler war von jedem anderen nicht zu unterscheiden (Audit ARC-2/API-2)."""
    gewartet: list[float] = []

    async def statt_schlaf(dauer):
        gewartet.append(dauer)

    monkeypatch.setattr(asyncio, "sleep", statt_schlaf)
    async with _mit_429("9") as client:
        with pytest.raises(RateLimitedError) as fehler:
            await client.text_of("https://example.org/")
    assert fehler.value.retry_after == 9.0
    assert gewartet == [9.0, 9.0], "zweimal gewartet, wie der Dienst sagte"


async def test_eine_zu_lange_wartezeit_wird_hier_ebenso_gereicht(monkeypatch):
    gewartet: list[float] = []

    async def statt_schlaf(dauer):
        gewartet.append(dauer)

    monkeypatch.setattr(asyncio, "sleep", statt_schlaf)
    async with _mit_429("3600") as client:
        with pytest.raises(RateLimitedError):
            await client.text_of("https://example.org/")
    assert gewartet == []


# --- SEC-4 und SEC-8: derselbe Massstab wie beim Transport ----------------


def test_extraction_lehnt_einen_folgenden_client_ab():
    """Audit SEC-4 -- die Wache stand nur im Transport."""
    with pytest.raises(EduSharingError, match="follow_redirects"):
        TextExtraction(BASE, client=httpx.AsyncClient(follow_redirects=True))


def test_extraction_lehnt_timeout_und_client_zusammen_ab():
    """``timeout`` wurde geprueft und dann mit dem Client verworfen -- der
    Parameter war eine Zusage, die niemand einhielt (Audit SEC-8)."""
    with pytest.raises(EduSharingError, match="timeout and client"):
        TextExtraction(BASE, timeout=0.5, client=httpx.AsyncClient())


def test_extraction_nimmt_den_client_allein():
    dienst = TextExtraction(BASE, client=httpx.AsyncClient())
    assert dienst._client is not None


# --- API-1: eine Umleitung ist kein "kein Text" --------------------------


async def test_eine_umleitung_ist_kein_fehlender_text():
    """Ein 3xx fiel in den Zweig unter 400, kam mit leerem Koerper bei
    ``_result`` an und wurde zu ``no_text`` -- also zu einer Aussage ueber die
    Seite, obwohl er eine ueber den Dienst ist. Ein falsch gesetzter Proxy sah
    damit aus wie eine Seite ohne Text (Audit API-1)."""
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://anderswo.test/"})

    client = TextExtraction(
        BASE, backoff_base=0.0, resolve=_oeffentlich,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with client:
        with pytest.raises(EduSharingError, match=r"anderswo.test"):
            await client.text_of("https://example.org/")


# --- SEC-3: dieselbe Adressregel wie im Agenten --------------------------


@pytest.mark.parametrize("adresse", [
    "http://127.0.0.1\\@example.com/",
    "http://user:pw@example.com/",
    "http://example.com\\@127.0.0.1/",
])
async def test_eine_adresse_die_der_agent_ablehnt_geht_auch_hier_nicht_raus(adresse):
    """Gemessen am 08.09.2026: ``urlsplit`` liest bei
    ``http://127.0.0.1\\@example.com/`` den Host als ``example.com`` -- die
    Pruefung sah einen harmlosen oeffentlichen Namen und reichte die Adresse
    **woertlich** an den Extraktionsdienst weiter. Ein WHATWG-Parser, wie ihn
    ``method="browser"`` dahinter benutzt, liest ``127.0.0.1``.

    Die zweite Form traegt Anmeldedaten zu einem fremden Dienst.
    ``agent.safety.is_safe_url`` lehnt alle drei ab, ``text_of`` nicht
    (Audit SEC-3)."""
    gesehen = []

    def handler(request):
        gesehen.append(request)
        return httpx.Response(200, json={"text": "sollte nie kommen"})

    client = TextExtraction(
        BASE, backoff_base=0.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with client:
        ergebnis = await client.text_of(adresse)
    assert ergebnis.reason == "unsafe_url", ergebnis.reason
    assert not gesehen, "die Adresse darf den Dienst nie erreichen"


async def test_eine_gewoehnliche_adresse_geht_weiterhin_durch():
    """Die Gegenprobe: die Wache darf nicht alles ablehnen."""
    def handler(request):
        return httpx.Response(200, json={"text": "Volltext", "lang": "de"})

    client = TextExtraction(
        BASE, backoff_base=0.0, resolve=_oeffentlich,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with client:
        ergebnis = await client.text_of("https://example.org/seite")
    assert ergebnis.text == "Volltext"


# --- F11 (Fremdpruefung 09.09.2026): wem gehoert der Client ----------------
#
# ``Transport`` und ``BildungsAPI`` merken sich seit jeher, ob sie den Client
# selbst gebaut haben, und schliessen nur dann. ``TextExtraction`` schloss
# immer -- gemessen am 09.09.2026 war ein eingebrachter Client nach
# ``aclose()`` geschlossen. Wer den Verbindungspool teilt, kann danach nichts
# mehr senden, und das ausgerechnet bei Dependency Injection, dem Fall, fuer
# den ``client=`` da ist.


def _leerer_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})))


async def test_ein_eingebrachter_client_bleibt_offen():
    geteilt = _leerer_client()
    dienst = TextExtraction("https://extraktion.test", client=geteilt)
    await dienst.aclose()
    assert geteilt.is_closed is False
    await geteilt.aclose()


async def test_ein_eingebrachter_client_ueberlebt_auch_den_kontextmanager():
    """``async with`` ruft dasselbe ``aclose`` -- der Weg, den ein Dienst mit
    eigenem Lebenszyklus tatsaechlich nimmt."""
    geteilt = _leerer_client()
    async with TextExtraction("https://extraktion.test", client=geteilt):
        pass
    assert geteilt.is_closed is False
    await geteilt.aclose()


async def test_ein_selbst_gebauter_client_wird_weiterhin_geschlossen():
    """Die Gegenprobe. Ohne sie waere die Wache gruen, wenn ``aclose()``
    ueberhaupt nichts mehr schliesst -- und der Pool bliebe bis zum Ende des
    Interpreters offen, was genau der Grund fuer die Methode ist."""
    dienst = TextExtraction("https://extraktion.test")
    async with dienst:
        pass
    assert dienst._client.is_closed is True


# --- Was der Dienst schickt, ist nicht, was er schicken soll ---------------

async def test_ein_unlesbarer_status_bleibt_im_vertrag():
    """``status`` kommt von einer fremden Maschine.

    ``text_of`` nennt zwei Ausgaenge: ein ``ExtractedText`` oder ein
    ``EduSharingError``. Ein ``ValueError`` aus ``int()`` ist keiner davon --
    und ``agent.result.as_result`` reicht alles weiter, was kein
    ``EduSharingError`` ist, sodass der Werkzeugaufruf abstuerzt statt zu
    antworten (Audit COR-20-1).
    """
    dienst = Dienst(body={"text": "Der Text.", "lang": "de", "status": "OK"})
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.test/seite")
    assert ergebnis.text == "Der Text."
    assert ergebnis.status == 0, "unlesbar heisst unbekannt, nicht kaputt"


async def test_ein_unlesbarer_status_im_424_bleibt_ebenso_im_vertrag():
    """Derselbe Weg noch einmal -- der 424 liest ``detail.status``."""
    dienst = Dienst(status=424, body={"detail": {"status": "424 Failed",
                                                 "error_message": "nichts zu holen"}})
    async with dienst.client(resolve=_oeffentlich) as client:
        ergebnis = await client.text_of("https://example.test/seite")
    assert ergebnis.reason == "no_text"
    assert ergebnis.status == 0
    assert ergebnis.detail == "nichts zu holen"


# --- Eine 200 ohne Antwortobjekt (Audit COR-23-3) ---------------------------

def _dahinter(antwort: httpx.Response) -> TextExtraction:
    return TextExtraction(BASE, resolve=_oeffentlich, client=httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: antwort)))


_ANMELDESEITE = httpx.Response(200, text="<!DOCTYPE html><html>Bitte anmelden</html>",
                               headers={"content-type": "text/html"})


async def test_eine_html_seite_mit_200_ist_ein_fehler_des_dienstes():
    """Audit COR-23-3 (23.09.2026): hinter einem Proxy, der mit seiner eigenen
    Seite antwortet, hiess jede Adresse ``reason="no_text"`` -- eine Aussage
    ueber die Seite, obwohl es eine ueber den Dienst ist. Dieselbe Verwechslung
    hat API-1 fuer eine Umleitung beseitigt."""
    async with _dahinter(_ANMELDESEITE) as client:
        with pytest.raises(ServerError, match="non-JSON"):
            await client.text_of("https://example.org/seite")


async def test_eine_200_mit_einer_liste_ist_ebenso_ein_fehler_des_dienstes():
    """JSON, aber nicht die Antwortform des Dienstes: auch daraus liest sich
    keine Aussage ueber die Seite."""
    async with _dahinter(httpx.Response(200, json=["kein", "objekt"])) as client:
        with pytest.raises(ServerError, match="list"):
            await client.text_of("https://example.org/seite")


async def test_ping_hinter_dem_proxy_bleibt_im_vertrag():
    """``ping`` las die Antwort ungeschuetzt -- gemessen
    ``json.decoder.JSONDecodeError``, ausserhalb jedes Vertrags."""
    async with _dahinter(_ANMELDESEITE) as client:
        with pytest.raises(ServerError):
            await client.ping()
