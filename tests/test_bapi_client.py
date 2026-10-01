"""Der b-api-Client.

Die b-api ist das LLM-Gateway von OpenEduHub. Gemessen (Staging): Auth per
``X-API-KEY``, zwei Provider, keine Quoten-Header, kein ``retry-after`` bei
429 -- ein Client sieht sein Restkontingent also nicht und merkt das Limit
erst am Fehler.
"""

import asyncio
import json
import logging
from datetime import date

import httpx
import pytest

from edusharing.bapi import CACHE_FOREVER, BildungsAPI
from edusharing.errors import (
    EduSharingError,
    RateLimitedError,
    ServerError,
    ValidationError,
)

#: Frei erfunden. Die Tests antworten ueber MockTransport; eine echte
#: Adresse hier waere eine Instanz im Code.
GATEWAY = "https://gateway.example.test"

MODELLE = {"data": [
    {"id": "glm-4.7", "demand": 2, "status": "ready", "input": ["text"], "output": ["text"]},
    {"id": "qwen3.6-35b-a3b", "demand": 0, "status": "ready",
     "input": ["text"], "output": ["text"]},
    {"id": "embed-x", "demand": 0, "status": "ready",
     "input": ["text"], "output": ["embedding"]},
]}
ANTWORT = {"choices": [{"message": {"content": "Die Antwort"}}],
           "usage": {"total_tokens": 42}}


def _client(handler, aufrufe=None, **kwargs):
    def wrapped(request):
        if aufrufe is not None:
            aufrufe.append(request)
        return handler(request)

    kwargs.setdefault("api_key", "geheimer-schluessel")
    kwargs.setdefault("base_url", GATEWAY)
    kwargs.setdefault("backoff_base", 0.0)
    kwargs.setdefault("models_cache_seconds", 0)
    return BildungsAPI(
        client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), **kwargs)


def _router(request):
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json=MODELLE)
    return httpx.Response(200, json=ANTWORT)


# --- Auth ------------------------------------------------------------------

async def test_schluessel_geht_als_x_api_key():
    """Der Client schickt X-API-KEY, und nur den. Gemessen 2026-10-01 nimmt
    die b-api auch einen Authorization-Bearer an (200) -- die fruehere Zeile
    hier, ein Bearer ergebe 401, stimmte nicht. Bei edu-sharing ist es
    andersherum: dort gilt Basic, und ein Bearer wird uebergangen."""
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.models()
    assert aufrufe[0].headers.get("x-api-key") == "geheimer-schluessel"
    assert "authorization" not in aufrufe[0].headers


async def test_schluessel_steht_nicht_im_repr():
    async with _client(_router) as api:
        assert "geheimer-schluessel" not in repr(api)


def test_fehlender_schluessel_wird_beim_bauen_gemeldet():
    with pytest.raises(EduSharingError, match="B_API_KEY"):
        BildungsAPI(api_key="", base_url=GATEWAY)


def test_from_env_ohne_schluessel(monkeypatch):
    monkeypatch.delenv("B_API_KEY", raising=False)
    with pytest.raises(EduSharingError, match="B_API_KEY"):
        BildungsAPI.from_env()


# --- Modelle ---------------------------------------------------------------

async def test_modelle_werden_gelesen():
    async with _client(_router) as api:
        modelle = await api.models()
    assert {m.id for m in modelle} == {"glm-4.7", "qwen3.6-35b-a3b", "embed-x"}
    assert next(m for m in modelle if m.id == "glm-4.7").demand == 2


async def test_modellliste_wird_kurz_zwischengespeichert():
    """demand schwankt im Minutentakt -- ein langer Cache wuerde die Wahl auf
    veralteten Zahlen treffen. Ganz ohne Cache kostet jeder Aufruf eine
    zusaetzliche Anfrage."""
    aufrufe = []
    async with _client(_router, aufrufe, models_cache_seconds=60) as api:
        await api.models()
        await api.models()
    assert len([r for r in aufrufe if r.url.path.endswith("/models")]) == 1


async def test_cache_laesst_sich_abschalten():
    aufrufe = []
    async with _client(_router, aufrufe, models_cache_seconds=0) as api:
        await api.models()
        await api.models()
    assert len([r for r in aufrufe if r.url.path.endswith("/models")]) == 2


# --- Chat ------------------------------------------------------------------

async def test_chat_mit_einfachem_text():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        antwort = await api.chat("Was ist Photosynthese?")
    assert antwort == "Die Antwort"
    body = json.loads(next(r for r in aufrufe if "completions" in r.url.path).content)
    assert body["messages"] == [{"role": "user", "content": "Was ist Photosynthese?"}]


async def test_chat_waehlt_das_am_wenigsten_ausgelastete_modell():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("hallo")
    body = json.loads(next(r for r in aufrufe if "completions" in r.url.path).content)
    assert body["model"] == "qwen3.6-35b-a3b"


async def test_festes_modell_spart_die_modellabfrage():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("hallo", model="glm-4.7")
    assert not any(r.url.path.endswith("/models") for r in aufrufe)


async def test_eigene_nachrichtenliste():
    aufrufe = []
    nachrichten = [{"role": "system", "content": "Du bist knapp."},
                   {"role": "user", "content": "hallo"}]
    async with _client(_router, aufrufe) as api:
        await api.chat(nachrichten, model="glm-4.7")
    body = json.loads(next(r for r in aufrufe if "completions" in r.url.path).content)
    assert body["messages"] == nachrichten


async def test_provider_ist_waehlbar():
    aufrufe = []
    async with _client(_router, aufrufe, provider="openai") as api:
        await api.models()
    assert "/llm/openai/models" in str(aufrufe[0].url)


# --- Fehler und Wiederholung ----------------------------------------------

@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_voruebergehende_fehler_werden_wiederholt(status):
    """429 kommt ohne retry-after -- moeglich ist nur exponentielles Warten."""
    versuche = []

    def handler(request):
        versuche.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        if len([r for r in versuche if "completions" in r.url.path]) < 3:
            return httpx.Response(status, json={"message": "gerade nicht"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, max_retries=3) as api:
        assert await api.chat("hallo", model="glm-4.7") == "Die Antwort"


async def test_dauerhafte_fehler_werden_nicht_wiederholt():
    """400 'not a chat model' wird beim vierten Versuch nicht besser."""
    versuche = []

    def handler(request):
        versuche.append(request)
        return httpx.Response(404, json={"message": "This is not a chat model"})

    async with _client(handler, max_retries=3) as api:
        with pytest.raises(EduSharingError):
            await api.chat("hallo", model="embed-x")
    assert len(versuche) == 1


async def test_ein_unbepreistes_modell_wird_nicht_wiederholt():
    """503 heisst sonst "gleich wieder da". Hier heisst es: dem Gateway fehlt
    eine Konfiguration -- und die entsteht nicht durchs Warten.

    Gemessen am 21.09.2026 gegen b-api.staging.openeduhub.net:
    ``apertus-70b-instruct-2509`` steht in ``/models``, meldet ``ready`` und
    Auslastung 0, wird also von ``least_loaded`` zuerst genannt -- und wird
    trotzdem nicht bedient. Der Aufruf kostete **15,0 s**, drei Versuche mit
    Backoff, wo ein bedientes Modell in 0,1 bis 0,9 s antwortet. Dieselbe
    Ueberlegung wie beim 404 in ``retry.RETRYABLE_STATUS``: das ist keine
    Wartezeit, das ist eine Antwort.
    """
    versuche = []

    def handler(request):
        versuche.append(request)
        return httpx.Response(503, json={"message":
            "Model pricing unavailable for 'apertus-70b-instruct-2509' "
            "- cannot enforce cost quota"})

    async with _client(handler, max_retries=3) as api:
        with pytest.raises(EduSharingError, match="pricing"):
            await api.chat("hallo", model="apertus-70b-instruct-2509")
    assert len(versuche) == 1


async def test_eine_gewoehnliche_503_wird_weiterhin_wiederholt():
    """Die Gegenprobe: ohne diesen Wortlaut bleibt 503 eine Ueberlastung."""
    versuche = []

    def handler(request):
        versuche.append(request)
        if len(versuche) < 2:
            return httpx.Response(503, json={"message": "upstream busy"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, max_retries=3) as api:
        assert await api.chat("hallo", model="glm-4.7") == "Die Antwort"
    assert len(versuche) == 2


async def test_fehlermeldung_nennt_die_ursache():
    def handler(request):
        return httpx.Response(400, json={"message": "use max_completion_tokens instead"})

    async with _client(handler) as api:
        with pytest.raises(EduSharingError, match="max_completion_tokens"):
            await api.chat("hallo", model="gpt-5.6-luna")


# --- Gleichzeitigkeit ------------------------------------------------------

async def test_gleichzeitigkeit_ist_begrenzt():
    """Gemessen: ab etwa 19 gleichzeitigen Anfragen kommen 502er, bei 28 bricht
    es ab. Die Grenze ist nicht stabil und gehoert nachgemessen -- aber
    unbegrenzt ist sicher falsch."""
    laufend = 0
    hoechststand = 0

    async def handler(request):
        nonlocal laufend, hoechststand
        laufend += 1
        hoechststand = max(hoechststand, laufend)
        await asyncio.sleep(0.01)
        laufend -= 1
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, max_concurrency=3) as api:
        await asyncio.gather(*(api.chat("x", model="glm-4.7") for _ in range(12)))
    assert hoechststand <= 3


# --- Wenn ein "bereites" Modell doch nicht antwortet ----------------------

async def test_automatische_wahl_weicht_auf_das_naechste_modell_aus():
    """Gemessen: apertus-70b-instruct-2509 meldet status 'ready' und demand 0,
    antwortet aber mit 503 'Model pricing unavailable ... cannot enforce cost
    quota'. status allein taugt also nicht als Auswahlkriterium, und die
    Untauglichkeit steht in keiner Modellliste.

    Wer die Wahl der Bibliothek ueberlassen hat, will eine Antwort -- nicht
    den Hinweis, dass ausgerechnet das erste Modell gerade nicht abrechenbar
    ist.
    """
    versuche = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        body = json.loads(request.content)
        versuche.append(body["model"])
        if body["model"] == "qwen3.6-35b-a3b":     # das am wenigsten ausgelastete
            return httpx.Response(503, json={"message": "Model pricing unavailable"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, max_retries=0) as api:
        assert await api.chat("hallo") == "Die Antwort"
    assert versuche == ["qwen3.6-35b-a3b", "glm-4.7"], versuche


async def test_festes_modell_weicht_nicht_aus():
    """Wer ein Modell nennt, will dessen Antwort -- eine vom Nachbarmodell
    waere ein stiller Austausch."""
    versuche = []

    def handler(request):
        versuche.append(json.loads(request.content)["model"])
        return httpx.Response(503, json={"message": "Model pricing unavailable"})

    async with _client(handler, max_retries=0) as api:
        with pytest.raises(EduSharingError):
            await api.chat("hallo", model="glm-4.7")
    assert versuche == ["glm-4.7"]


async def test_wenn_alle_modelle_scheitern_wird_das_gesagt():
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        return httpx.Response(503, json={"message": "Model pricing unavailable"})

    async with _client(handler, max_retries=0) as api:
        with pytest.raises(EduSharingError, match="None of the models"):
            await api.chat("hallo")


async def test_gewaehltes_modell_ist_ablesbar():
    """Sonst weiss der Aufrufer nicht, wessen Antwort er gerade liest."""
    async with _client(_router) as api:
        await api.chat("hallo")
        assert api.last_model == "qwen3.6-35b-a3b"


# --- Parametervalidierung -------------------------------------------------
#
# Audit-Befund F2/F3 vom 27.08.2026: der b-api-Client nahm jeden Parameter
# ungeprueft, waehrend der Transport vier davon prueft. max_retries=-1 liess die
# Retry-Schleife nie laufen und endete in einem "assert last is not None" --
# unter "python -O" wird daraus ein "raise None" und damit ein TypeError statt
# der eigentlichen Fehlermeldung.

@pytest.mark.parametrize("kwargs", [
    {"max_retries": -1},
    {"max_concurrency": 0},
    {"timeout": 0},
    {"backoff_base": -1},
    {"models_cache_seconds": -1},
])
def test_unsinnige_parameter_werden_sofort_abgelehnt(kwargs):
    """Frueh und laut statt spaet und raetselhaft -- dieselbe Regel, nach der
    sich der Transport richtet."""
    with pytest.raises(EduSharingError) as fehler:
        BildungsAPI(api_key="k", base_url=GATEWAY, **kwargs)
    # Die Meldung muss den Parameter benennen, sonst hilft sie nicht.
    assert next(iter(kwargs)) in str(fehler.value)


def test_gueltige_grenzwerte_bleiben_erlaubt():
    """Gegenprobe: 0 Wiederholungen und 0 Sekunden Cache sind sinnvoll."""
    api = BildungsAPI(api_key="k", base_url=GATEWAY, max_retries=0,
                      backoff_base=0,
                      models_cache_seconds=0, max_concurrency=1)
    assert api.max_retries == 0


async def test_modellwechsel_wird_gemeldet(caplog):
    """Audit-Befund F5: bei automatischer Wahl sagte nur last_model, wessen
    Antwort man liest -- warum die vorherigen Kandidaten ausfielen, stand
    nirgends. Genau das braucht man nach einem Zwischenfall.
    """
    import logging

    caplog.set_level(logging.INFO, logger="edusharing")

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        if json.loads(request.content)["model"] == "qwen3.6-35b-a3b":
            return httpx.Response(503, json={"message": "Model pricing unavailable"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler) as api:
        await api.chat("hallo")

    meldungen = [r.getMessage() for r in caplog.records]
    assert any("qwen3.6-35b-a3b" in m for m in meldungen), meldungen
    # Der Schluessel gehoert niemals hinein.
    assert "geheimer-schluessel" not in "\n".join(meldungen)


def test_ohne_adresse_wird_verweigert(monkeypatch):
    """Kein Vorgabewert fuer das Gateway -- wie beim Extraktionsdienst.

    Bis zum 28.08.2026 stand hier ``https://b-api.staging.openeduhub.net`` als
    Standard. Wer ``B_API_KEY`` setzte und sonst nichts, schickte seinen
    Schluessel damit an eine fremde **Staging**-Instanz, ohne sie gewaehlt zu
    haben. Das Schwestermodul ``extraction`` verweigert genau das seit jeher mit
    derselben Begruendung; die beiden Dienste widersprachen sich im selben
    Projekt.
    """
    monkeypatch.setenv("B_API_KEY", "irgendein-schluessel")
    monkeypatch.delenv("B_API_BASE_URL", raising=False)
    with pytest.raises(EduSharingError) as fehler:
        BildungsAPI.from_env()
    assert "B_API_BASE_URL" in str(fehler.value)


def test_zugangsdaten_in_der_adresse_werden_abgewiesen():
    """SEC-1: ``base_url`` wurde bisher gar nicht geprueft."""
    with pytest.raises(EduSharingError) as fehler:
        BildungsAPI("irgendein-schluessel", base_url="https://alice:geheim@b-api.example.test")
    assert "geheim" not in str(fehler.value)


def test_mit_adresse_aus_der_umgebung_geht_es(monkeypatch):
    monkeypatch.setenv("B_API_KEY", "irgendein-schluessel")
    monkeypatch.setenv("B_API_BASE_URL", "https://gateway.example.test")
    llm = BildungsAPI.from_env()
    assert llm.base_url == "https://gateway.example.test"


# --- reasoning_effort und verbosity durchreichen ---------------------------

async def test_chat_setzt_die_vorgabe_low_bei_einem_reasoning_modell():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("x", model="gpt-5.6-luna", provider="openai")
    koerper = json.loads(aufrufe[-1].content)
    assert koerper["reasoning_effort"] == "low"
    assert koerper["verbosity"] == "low"


async def test_chat_laesst_sie_weg_wo_das_modell_sie_nicht_kennt():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("x", model="gpt-4o-mini", provider="openai")
    koerper = json.loads(aufrufe[-1].content)
    assert "reasoning_effort" not in koerper
    assert "verbosity" not in koerper


async def test_chat_reicht_einen_ausdruecklichen_wert_durch():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("x", model="gpt-5.6-luna", provider="openai",
                       reasoning_effort="high")
    assert json.loads(aufrufe[-1].content)["reasoning_effort"] == "high"


async def test_chat_verwirft_einen_ausdruecklichen_wunsch_nicht_still():
    async with _client(_router) as api:
        with pytest.raises(ValidationError) as info:
            await api.chat("x", model="gpt-4o-mini", provider="openai",
                           reasoning_effort="high")
    assert "gpt-4o-mini" in str(info.value)


# --- Virtuelles Modell -----------------------------------------------------
#
# Der Aufrufer nennt zwei oder drei Modelle, die alle taugen wuerden; die
# Bibliothek nimmt daraus das am wenigsten ausgelastete. In MODELLE oben hat
# qwen3.6-35b-a3b demand=0 und glm-4.7 demand=2.

async def test_liste_waehlt_das_am_wenigsten_ausgelastete():
    aufrufe = []
    async with _client(_router, aufrufe) as api:
        await api.chat("x", model=["glm-4.7", "qwen3.6-35b-a3b"])
    assert json.loads(aufrufe[-1].content)["model"] == "qwen3.6-35b-a3b"


async def test_benannter_verbund_wird_aufgeloest():
    aufrufe = []
    async with _client(_router, aufrufe,
                       virtual_models={"schnell": ["glm-4.7", "qwen3.6-35b-a3b"]}) as api:
        await api.chat("x", model="schnell")
    assert json.loads(aufrufe[-1].content)["model"] == "qwen3.6-35b-a3b"


async def test_ein_verbundname_der_wie_ein_echtes_modell_heisst_faellt_auf():
    """Sonst haengt es vom Nachschlagen ab, welches von beiden gemeint war."""
    async with _client(_router,
                       virtual_models={"glm-4.7": ["qwen3.6-35b-a3b"]}) as api:
        with pytest.raises(EduSharingError) as info:
            await api.chat("x", model="glm-4.7")
    assert "glm-4.7" in str(info.value)


async def test_faellt_das_erste_modell_aus_kommt_das_zweite_dran():
    """Genau dafuer nennt man mehrere."""
    aufrufe = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        if b"qwen3.6-35b-a3b" in request.content:
            return httpx.Response(503, json={"error": "Model pricing unavailable"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, aufrufe) as api:
        antwort = await api.chat("x", model=["qwen3.6-35b-a3b", "glm-4.7"])
    assert antwort == "Die Antwort"

    # Der Reihe nach, ohne die Wiederholungen: ein 503 ist wiederholbar, also
    # versucht der Transport dasselbe Modell erst mehrfach. Fuer einen Verbund
    # ist das nicht ideal -- wechseln waere billiger als warten -- aber es ist
    # bestehendes Verhalten und gehoert nicht in diese Aenderung.
    gefragt = [json.loads(r.content)["model"] for r in aufrufe
               if not r.url.path.endswith("/models")]
    ohne_wiederholung = [m for i, m in enumerate(gefragt)
                         if i == 0 or m != gefragt[i - 1]]
    assert ohne_wiederholung == ["qwen3.6-35b-a3b", "glm-4.7"]


async def test_ein_unbekannter_name_im_verbund_wird_gemeldet():
    async with _client(_router) as api:
        with pytest.raises(EduSharingError) as info:
            await api.chat("x", model=["glm-4.7", "gibt-es-nicht"])
    assert "gibt-es-nicht" in str(info.value)


# --- Wann die Auslastung abgefragt wird ------------------------------------
#
# ``demand`` bewegt sich im Minutentakt, also ist die Vorgabe ein kurzer Cache
# (30 s). Wer ein kurzes Skript schreibt, will die Zahlen genau einmal holen;
# wer einen langlaufenden Dienst schreibt, will sie nicht veralten lassen. Das
# ist dieselbe Stellschraube, nur anders gestellt.

async def test_cache_forever_fragt_die_modelle_genau_einmal():
    aufrufe = []
    async with _client(_router, aufrufe,
                       models_cache_seconds=CACHE_FOREVER) as api:
        await api.models()
        await api.models()
        await api.models()
    assert sum(1 for r in aufrufe if r.url.path.endswith("/models")) == 1


async def test_ohne_cache_wird_jedes_mal_gefragt():
    aufrufe = []
    async with _client(_router, aufrufe, models_cache_seconds=0) as api:
        await api.models()
        await api.models()
    assert sum(1 for r in aufrufe if r.url.path.endswith("/models")) == 2


# --- Der Auslastungsbericht ------------------------------------------------

async def test_load_meldet_die_modelle_am_wenigsten_ausgelastet_zuerst():
    async with _client(_router) as api:
        bericht = await api.load()
    assert [m.id for m in bericht.models] == ["qwen3.6-35b-a3b", "glm-4.7"]
    assert bericht.least_loaded is not None
    assert bericht.least_loaded.id == "qwen3.6-35b-a3b"
    assert bericht.reports_load is True


async def test_load_sagt_wenn_es_gar_keine_auslastung_gibt():
    """Bei OpenAI ist ``demand`` nicht vorhanden -- dann ist der ganze Bericht
    fuer die Lastfrage wertlos, und das muss dastehen."""
    ohne = {"data": [{"id": "gpt-5.6-luna"}, {"id": "gpt-4o-mini"}]}

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=ohne)
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler) as api:
        bericht = await api.load()
    assert bericht.reports_load is False
    assert "gpt-5.6-luna" in bericht.summary()


async def test_der_bericht_nennt_abgekuendigte_modelle():
    mit_datum = {"data": [{"id": "gpt-4", "shutdown_date": "2026-01-01"}]}

    def handler(request):
        return httpx.Response(200, json=mit_datum)

    async with _client(handler) as api:
        bericht = await api.load(on=date(2026, 6, 1))
    assert bericht.retired == ("gpt-4",)
    assert "gpt-4" in bericht.summary()


# --- Wiederholen oder wechseln ---------------------------------------------
#
# Ein 503 ist wiederholbar, also versuchte der Transport dasselbe ausgelastete
# Modell dreimal, bevor er wechselte -- bei backoff_base 2.5 rund 17 s, obwohl
# ein anderes Modell danebenstand. Wer mehrere Modelle nennt, will wechseln.
#
# Der Beispieltext ist seit dem 21.09.2026 keine Nebensache mehr: seit
# ``_will_not_change`` unterscheidet die Bibliothek zwei 503. Hier geht es um
# **Auslastung**, also muss hier auch Auslastung stehen -- vorher stand
# "Model pricing unavailable" darin, und das meldet gerade keine. Der Fall
# darunter prueft den anderen Wortlaut.

def _immer_503(aufrufe):
    def handler(request):
        aufrufe.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        return httpx.Response(503, json={"error": "upstream busy"})
    return handler


def _versuche_je_modell(aufrufe):
    from collections import Counter
    return Counter(json.loads(r.content)["model"] for r in aufrufe
                   if not r.url.path.endswith("/models"))


async def test_ein_kandidat_wird_einmal_wiederholt_dann_gewechselt():
    aufrufe = []
    async with _client(_immer_503(aufrufe), max_retries=3) as api:
        with pytest.raises(EduSharingError):
            await api.chat("x", model=["qwen3.6-35b-a3b", "glm-4.7"])
    zaehler = _versuche_je_modell(aufrufe)
    # Der erste: ein Versuch plus eine Wiederholung.
    assert zaehler["qwen3.6-35b-a3b"] == 2
    # Der letzte: das volle Budget, denn danach kommt nichts mehr.
    assert zaehler["glm-4.7"] == 4


async def test_das_budget_je_kandidat_ist_einstellbar():
    aufrufe = []
    async with _client(_immer_503(aufrufe), max_retries=3,
                       retries_before_switching=0) as api:
        with pytest.raises(EduSharingError):
            await api.chat("x", model=["qwen3.6-35b-a3b", "glm-4.7"])
    assert _versuche_je_modell(aufrufe)["qwen3.6-35b-a3b"] == 1


async def test_ein_einzelnes_modell_behaelt_das_volle_budget():
    """Ohne Alternative gibt es nichts zu wechseln -- warten ist alles."""
    aufrufe = []
    async with _client(_immer_503(aufrufe), max_retries=2) as api:
        with pytest.raises(EduSharingError):
            await api.chat("x", model="glm-4.7")
    assert _versuche_je_modell(aufrufe)["glm-4.7"] == 3


async def test_ein_unbepreistes_modell_wird_sofort_gewechselt():
    """Der Unterschied, den ``_will_not_change`` ausmacht.

    Ausgelastet kostet der erste Kandidat zwei Versuche (oben). Unbepreist
    kostet er einen: die Antwort wird beim vierten Mal nicht anders, und
    daneben steht ein Modell, das antwortet. Gemessen am 21.09.2026 gegen
    staging waren das 15,0 s gegenueber 0,1 bis 0,9 s -- und der Aufrufer,
    der die Wahl der Bibliothek ueberlassen hat, bekommt seine Antwort
    entsprechend frueher.
    """
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        if json.loads(request.content)["model"] == "qwen3.6-35b-a3b":
            return httpx.Response(503, json={"error": "Model pricing unavailable"})
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, max_retries=3) as api:
        antwort = await api.chat("x", model=["qwen3.6-35b-a3b", "glm-4.7"])
    assert antwort == "Die Antwort"
    assert _versuche_je_modell(aufrufe)["qwen3.6-35b-a3b"] == 1


async def test_ein_verbund_probiert_alle_seine_mitglieder():
    """Wer fuenf nennt, meint fuenf -- die Obergrenze gilt der automatischen
    Wahl, nicht einer ausdruecklichen Aufzaehlung."""
    viele = {"data": [{"id": f"m{i}", "demand": i, "status": "ready",
                       "input": ["text"], "output": ["text"]} for i in range(5)]}
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=viele)
        return httpx.Response(503, json={"error": "weg"})

    async with _client(handler, max_retries=0) as api:
        with pytest.raises(EduSharingError):
            await api.chat("x", model=["m0", "m1", "m2", "m3", "m4"])
    assert set(_versuche_je_modell(aufrufe)) == {"m0", "m1", "m2", "m3", "m4"}


async def test_gleichzeitige_aufrufe_holen_die_modelliste_nur_einmal():
    """Sonst stimmt die Zusage von CACHE_FOREVER nicht.

    Die Sperre allein reicht nicht: sie reiht die Aufrufer auf, aber jeder
    holt danach trotzdem. Die Pruefung muss INNERHALB der Sperre wiederholt
    werden.

    Die Attrappe muss dafuer wirklich unterbrechen. Eine synchrone laeuft
    durch, bevor die naechste Coroutine startet -- der Test koennte den
    Fehler dann gar nicht zeigen, und genau so hat er sich beim ersten
    Versuch versteckt.
    """
    anfragen = []

    async def handler(request):
        anfragen.append(request)
        await asyncio.sleep(0.02)
        return httpx.Response(200, json=MODELLE)

    api = BildungsAPI("k", base_url=GATEWAY, models_cache_seconds=CACHE_FOREVER,
                      client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    async with api:
        await asyncio.gather(*(api.models() for _ in range(6)))
    assert len(anfragen) == 1, f"{len(anfragen)} Anfragen statt einer"


# --- Jeder Fehlschlag ist ein EduSharingError ------------------------------
#
# Die Referenz sagt: "Every failure is an EduSharingError. Catch that one to
# catch them all." Zwei der drei Wege hielten das nicht ein -- und zwar
# uneinheitlich, denn der dritte im selben Aufruf hielt es.

@pytest.mark.parametrize("ruf", [
    "chat_ausdruecklicher_wunsch",
    "respond_ausdruecklicher_wunsch",
    "chat_unbekanntes_modell_im_verbund",
])
async def test_jeder_fehlschlag_ist_als_edusharingerror_fangbar(ruf):
    alt = {"data": [{"id": "gpt-4o-mini", "status": "ready",
                     "input": ["text"], "output": ["text"]}]}

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=alt)
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, provider="openai") as api:
        with pytest.raises(EduSharingError):
            if ruf == "chat_ausdruecklicher_wunsch":
                await api.chat("x", model="gpt-4o-mini", reasoning_effort="high")
            elif ruf == "respond_ausdruecklicher_wunsch":
                await api.respond("x", model="gpt-4o-mini", reasoning_effort="high")
            else:
                await api.chat("x", model=["gibt-es-nicht"])


async def test_chat_raet_nicht_wo_es_nichts_zu_ranken_gibt():
    """Der Fall, den der Test in test_bapi_models.py NICHT abdeckte.

    Dort steht der Waechter in ``pick_model`` -- aber ``chat`` ruft
    ``rank_models`` direkt. Der Unit-Test war gruen, der echte Weg griff
    weiterhin zu babbage-002. Deshalb hier, an der Stelle, die Nutzer benutzen.
    """
    ohne_angaben = {"data": [{"id": i} for i in
                             ("babbage-002", "gpt-5.6-luna", "dall-e-2")]}

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=ohne_angaben)
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler, provider="openai") as api:
        with pytest.raises(EduSharingError) as info:
            await api.chat("x")
    assert "model=" in str(info.value)
    assert api.last_model is None, "es wurde nichts gewaehlt"


async def test_chat_waehlt_weiter_wo_es_eine_grundlage_gibt():
    """Die Gegenprobe: MODELLE meldet demand und output, also bleibt alles."""
    async with _client(_router) as api:
        await api.chat("x")
    assert api.last_model == "qwen3.6-35b-a3b"


# --- Abgekuendigte Modelle in der Wahl -------------------------------------
#
# Gemessen am 31.08.2026: 19 der 132 OpenAI-Modelle waren an dem Tag bereits
# ueber ihr shutdown_date hinaus und standen weiter in der Liste. Sie
# auszuschliessen waere falsch -- sie antworten noch, und wer eines
# ausdruecklich nennt, meint es. Aber wenn die BIBLIOTHEK eines waehlt, muss
# das jemand erfahren koennen.

MIT_ABKUENDIGUNG = {"data": [
    {"id": "alt-aber-frei", "demand": 0, "status": "ready",
     "input": ["text"], "output": ["text"], "shutdown_date": "2020-01-01"},
    {"id": "neu-aber-voll", "demand": 5, "status": "ready",
     "input": ["text"], "output": ["text"]},
]}


async def test_eine_automatische_wahl_meldet_ein_abgekuendigtes_modell(caplog):
    caplog.set_level(logging.WARNING, logger="edusharing")

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MIT_ABKUENDIGUNG)
        return httpx.Response(200, json=ANTWORT)

    async with _client(handler) as api:
        await api.chat("x")

    assert api.last_model == "alt-aber-frei", "die Wahl bleibt die Wahl"
    meldungen = [r.getMessage() for r in caplog.records]
    assert any("alt-aber-frei" in m and "2020-01-01" in m for m in meldungen), meldungen


async def test_ein_lebendes_modell_wird_nicht_gemeldet(caplog):
    caplog.set_level(logging.WARNING, logger="edusharing")
    async with _client(_router) as api:
        await api.chat("x")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


# --- ARC-2/API-2: dieselbe Regel wie im Transport ---------------------------


async def test_ein_429_kommt_als_rate_limited_error_mit_der_wartezeit():
    """Gemessen antwortet die b-api ohne ``Retry-After``; nennt sie doch eine
    Zahl, wird sie gelesen statt geraten (Audit API-2)."""
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "5"},
                              json={"message": "API rate limit exceeded"})

    async with _client(handler, max_retries=0) as client:
        with pytest.raises(RateLimitedError) as fehler:
            await client.models()
    assert fehler.value.status == 429
    assert fehler.value.retry_after == 5.0
    assert "rate limit" in str(fehler.value)


async def test_eine_zu_lange_wartezeit_wird_nicht_abgewartet(monkeypatch):
    gewartet: list[float] = []

    async def statt_schlaf(dauer):
        gewartet.append(dauer)

    monkeypatch.setattr(asyncio, "sleep", statt_schlaf)

    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "3600"})

    async with _client(handler, max_retries=2) as client:
        with pytest.raises(RateLimitedError):
            await client.models()
    assert gewartet == []


# --- SEC-4 und SEC-8: derselbe Massstab wie beim Transport ----------------


def test_bapi_lehnt_einen_folgenden_client_ab():
    """Der Fall, an dem der Befund gemessen wurde: der X-API-KEY geht bei
    einer Umleitung ueber Ursprungsgrenzen mit (Audit SEC-4)."""
    with pytest.raises(EduSharingError, match="follow_redirects"):
        BildungsAPI(api_key="k", base_url=GATEWAY,
                    client=httpx.AsyncClient(follow_redirects=True))


def test_bapi_lehnt_timeout_und_client_zusammen_ab():
    """Audit SEC-8."""
    with pytest.raises(EduSharingError, match="timeout and client"):
        BildungsAPI(api_key="k", base_url=GATEWAY, timeout=0.5,
                    client=httpx.AsyncClient())


# --- API-1: 3xx und Nicht-JSON ------------------------------------------


async def test_bapi_meldet_eine_umleitung_statt_ihr_zu_folgen():
    """Ein Gateway, das umleitet, nahm den X-API-KEY mit, sobald jemand einen
    folgenden Client mitbrachte -- und ohne Wache sah der Aufrufer nur einen
    leeren Koerper (Audit API-1, SEC-4)."""
    def handler(request):
        return httpx.Response(302, headers={"Location": "https://anderswo.test/"})

    async with _client(handler) as api:
        with pytest.raises(EduSharingError, match=r"anderswo.test"):
            await api.models()


async def test_bapi_meldet_einen_html_koerper_als_servererror():
    def handler(request):
        return httpx.Response(200, text="<html>Loginseite</html>")

    async with _client(handler) as api:
        with pytest.raises(ServerError, match="non-JSON"):
            await api.models()


# --- F13 (Fremdpruefung 09.09.2026): eine Fehlerantwort ohne Objektform ----
#
# ``_error`` rief nach gelungenem ``response.json()`` ungeprueft ``.get()``.
# Gueltiges JSON muss aber kein Objekt sein, und das ``except ValueError``
# faengt diesen Formfehler nicht. Gemessen am 09.09.2026 ergab HTTP 429 mit
# ``['slow down']`` einen ``AttributeError: 'list' object has no attribute
# 'get'`` statt eines ``RateLimitedError`` -- die statusabhaengige
# Fehlerbehandlung war damit umgangen, und eine abweichende
# Gateway-Fehlerseite genuegt dafuer.
#
# Die edu-sharing-Seite hatte diesen Fall laengst richtig: ``_parse_body``
# prueft ``isinstance(data, dict)``. Nur die b-api-Seite nicht.

FEHLERFORMEN = [
    ('{"message": "zu schnell"}', "zu schnell"),
    ("[\"slow down\"]", None),
    ('"nur ein string"', None),
    ("null", None),
    ("{kein json", None),
    ("<html>Gateway Timeout</html>", None),
]


@pytest.mark.parametrize("koerper,erwartet", FEHLERFORMEN)
async def test_jede_fehlerform_bleibt_im_vertrag(koerper, erwartet):
    """Sechs Formen, eine Bibliotheksausnahme -- und der Status entscheidet
    ueber die Klasse, nicht das Format der Nachricht.

    Ueber ``models()``, weil ``chat()`` seine Fehler in die Modellumschaltung
    einwickelt und die Klasse dort nicht mehr sichtbar ist.
    """
    def handler(request):
        return httpx.Response(429, content=koerper.encode(),
                              headers={"retry-after": "7"})

    async with _client(handler, max_retries=0) as client:
        with pytest.raises(RateLimitedError) as fehler:
            await client.models()
    assert fehler.value.status == 429
    assert fehler.value.retry_after == 7.0, "Retry-After haengt nicht am Format"
    if erwartet is not None:
        assert erwartet in str(fehler.value)


async def test_die_objektform_wird_weiterhin_ausgelesen():
    """Die Gegenprobe. Ohne sie waere die Wache gruen, wenn ``_error`` die
    Nachricht gar nicht mehr liest und immer den Rohtext nimmt."""
    def handler(request):
        return httpx.Response(400, json={"error": "BadModel",
                                         "message": "kenne ich nicht"})

    async with _client(handler, max_retries=0) as client:
        with pytest.raises(EduSharingError) as fehler:
            await client.models()
    assert "kenne ich nicht" in str(fehler.value)


async def test_auch_ueber_chat_entkommt_keine_implementierungsausnahme():
    """Der Weg, den der Bericht genommen hat. ``chat()`` wickelt die Klasse in
    die Modellumschaltung ein -- ein ``AttributeError`` waere trotzdem einer,
    und der steht in keinem Vertrag."""
    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELLE)
        return httpx.Response(429, json=["slow down"])

    async with _client(handler, max_retries=0) as client:
        with pytest.raises(EduSharingError):
            await client.chat("hallo")


# --- Die Ablehnung des Anbieters (11.09.2026) ------------------------------


async def test_die_ablehnung_des_anbieters_liest_sich_als_satz():
    """Gemessen am 11.09.2026 gegen Staging: lehnt der Anbieter ab, reicht die
    b-api seinen Fehler unveraendert durch -- ``{"error": {"message": ...,
    "type": ...}}``, ohne ``message`` obenauf. So kam es bei ``responses`` mit
    ``messages`` statt ``input`` (openai und academiccloud) und bei
    ``chat/completions`` ohne ``messages``. In der Meldung soll der Satz
    stehen, nicht die Python-Darstellung des Objekts drumherum -- so, wie der
    Template-Modus ihn schon ausliest."""
    satz = ("Unsupported parameter: 'messages'. In the Responses API, this "
            "parameter has moved to 'input'.")

    def handler(request):
        return httpx.Response(400, json={"error": {
            "message": satz, "type": "invalid_request_error", "param": None,
            "code": "unsupported_parameter"}})

    koerper = {"model": "gpt-5.6-luna", "messages": [{"role": "user", "content": "hi"}]}
    async with _client(handler, max_retries=0) as api:
        with pytest.raises(ValidationError) as fehler:
            await api.call("responses", koerper, provider="openai")
    assert satz in str(fehler.value)
    assert "invalid_request_error" not in str(fehler.value)


# --- Der Proxy bleibt, wie er ist (Template-Modus, 11.09.2026) -----------

#: Gemessen am 11.09.2026, bevor der Template-Modus dazukam -- an einer
#: Instanz: die Methoden und die Attribute, die ``__init__`` setzt.
PROXY_FLAECHE = frozenset({
    # B01 adds binary responses without coupling the proxy to template mode.
    # B01 fuegt Binaerantworten hinzu; call_multipart am 21.09.2026 die vier
    # weitergeleiteten Routen, die eine Datei statt JSON nehmen.
    "aclose", "call", "call_bytes", "call_multipart", "chat", "embeddings",
    "from_env", "images", "load", "models", "moderate", "respond",
    "backoff_base", "base_url", "last_model", "max_retries",
    "models_cache_seconds", "provider", "retries_before_switching",
    "virtual_models",
    # Das Routing der B-API am 01.10.2026: die Routen des Kontos lesen und
    # verwalten, und der Antwort-Cache des Gateways -- bewusst am Proxy, denn
    # der Router ist fuer das Gateway ein dritter Provider.
    "routes", "create_route", "replace_route", "delete_route", "gateway_cache",
})


async def test_die_flaeche_des_proxys_bleibt_unveraendert():
    """Der Template-Modus steht neben dem Proxy, nicht in ihm.

    Die Vorgabe war: beide unabhaengig nutzbar, **kein Nachteil fuer den
    Proxy**. Ein neuer oeffentlicher Name an ``BildungsAPI`` wuerde die beiden
    koppeln; ein verschwundener waere ein Bruch. Beides faellt hier auf -- und
    wer den Proxy bewusst erweitert, traegt den Namen hier nach und sagt damit,
    dass er es wollte.

    An einer **Instanz** gemessen, nicht an der Klasse (Review 11.09.2026):
    ``dir(BildungsAPI)`` sieht nichts, was ``__init__`` setzt. Ein
    ``self.templates = ...`` dort -- genau die ausgeschlossene Kopplung -- kam
    an der alten Fassung dieser Wache gruen vorbei.
    """
    async with _client(lambda _request: httpx.Response(200)) as api:
        oeffentlich = {n for n in dir(api) if not n.startswith("_")}
    assert oeffentlich == PROXY_FLAECHE, (
        f"dazugekommen: {sorted(oeffentlich - PROXY_FLAECHE)}, "
        f"weggefallen: {sorted(PROXY_FLAECHE - oeffentlich)}")


async def test_der_modellspeicher_gehoert_nicht_dem_aufrufer():
    """Eine zurueckgegebene Liste gehoert dem, der sie bekommt.

    Gab ``models()`` den Zwischenspeicher selbst heraus, leerte ein
    ``.clear()`` des Aufrufers ihn fuer alle -- unter ``CACHE_FOREVER``
    dauerhaft, und die automatische Modellwahl endete danach in "No ready text
    model". Dieselbe Klasse wie F02 beim Vokabular (Audit MNT-20-1).
    """
    aufrufe = []
    llm = _client(_router, aufrufe, models_cache_seconds=CACHE_FOREVER)
    erste = await llm.models()
    erste.clear()
    zweite = await llm.models()
    assert [m.id for m in zweite] == ["glm-4.7", "qwen3.6-35b-a3b", "embed-x"]
    assert len(aufrufe) == 1, "der zweite Aufruf kam aus dem Zwischenspeicher"


@pytest.mark.parametrize("wert", [
    "gateway.example.test",                  # ohne Schema
    "ftp://gateway.example.test",
    "https://gateway.example.test/?x=1",
    "   ",
])
def test_eine_unbrauchbare_gateway_adresse_wird_abgelehnt(wert):
    """Gemessen (Audit SEC-20-1): ``ftp://...`` wurde angenommen und die
    Anfrage mitsamt ``X-API-KEY`` gebaut, ``.../?x=1`` schob die Route in den
    Query, und ein blanker Host endete nach dem vollen Wiederholungsbudget in
    einem ``ValueError`` aus der Standardbibliothek. Die drei
    Geschwisterclients weisen genau das seit jeher ab.
    """
    with pytest.raises(EduSharingError):
        BildungsAPI("schluessel", base_url=wert)
