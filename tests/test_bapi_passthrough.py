"""Die OpenAI-vertraeglichen Routen, die das Gateway durchreicht.

Gemessen am 28.08.2026 gegen b-api.staging.openeduhub.net. Die Spezifikation
taugt dafuer **nicht**: ``/v3/api-docs`` selbst beschreibt nur die eigenen
Controller des Gateways, und die Gruppen je Anbieter (``/v3/api-docs/openai``,
``.../academiccloud``) beschreiben die OpenAI-Oberflaeche, nicht was
durchgereicht wird -- die der AcademicCloud nennt ``/embeddings``, das dort 404
antwortet (gemessen 11.09.2026). Ermittelt wurde die Liste stattdessen mit
absichtlich leeren Rumpfen, an denen jede Route vor der Arbeit scheitert:

    403  Spring Security -- die Route steht NICHT auf der Positivliste
    400  die Route greift und bemaengelt die Anfrage
    429  Kontingent -- greift ebenfalls

Ergebnis: chat/completions, completions, embeddings, moderations, responses,
images/generations, images/edits, audio/*, files, batches, fine_tuning/jobs und
vector_stores werden durchgereicht. **Nicht** durchgereicht wird ``rerank`` --
403, wie eine frei erfundene Route. ``images/variations`` antwortet 404 von
OpenAI selbst, der Endpunkt ist dort abgekuendigt.
"""

import httpx
import pytest

from edusharing.bapi import BildungsAPI, Moderation
from edusharing.errors import EduSharingError, ValidationError

GATEWAY = "https://gateway.example.test"

EINBETTUNG = {
    "object": "list",
    "model": "text-embedding-3-small",
    "data": [
        {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
        {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
    ],
    "usage": {"prompt_tokens": 4, "total_tokens": 4},
}

MODERATION = {
    "id": "modr-1",
    "model": "omni-moderation-latest",
    "results": [{
        "flagged": True,
        "categories": {"hate": False, "violence": True, "sexual": False},
        "category_scores": {"hate": 0.01, "violence": 0.98, "sexual": 0.0},
    }],
}

BILDER = {"created": 1, "data": [
    {"url": "https://beispiel.test/a.png", "revised_prompt": "ein Baum"},
    {"b64_json": "aGFsbG8="},
]}

#: Die gemessene Form: ein Bild von ``gpt-image-1.5`` am 21.09.2026, in den
#: Zahlen gekuerzt und in den Feldern vollstaendig. Sie steht hier, weil die
#: Probe darueber genau das pruefen soll, was wirklich ankommt -- ``url`` ist
#: nicht dabei, und das ist kein Versehen: die GPT-Bildmodelle liefern immer
#: base64.
BILD_GEMESSEN = {
    "created": 1790013044,
    "background": "opaque",
    "output_format": "jpeg",
    "quality": "low",
    "size": "1024x1024",
    "usage": {"input_tokens": 10, "output_tokens": 376, "total_tokens": 386},
    "data": [{"b64_json": "aGFsbG8=",
              "generation_id": "75f3ab8b-be37-4268-b77b-75a062b29322"}],
}


def _client(handler, aufrufe=None, **kwargs):
    def wrapped(request):
        if aufrufe is not None:
            aufrufe.append(request)
        return handler(request)

    kwargs.setdefault("api_key", "geheimer-schluessel")
    kwargs.setdefault("base_url", GATEWAY)
    kwargs.setdefault("backoff_base", 0.0)
    return BildungsAPI(
        client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), **kwargs)


def _antwortet(nutzlast, status=200):
    return lambda _request: httpx.Response(status, json=nutzlast)


# --- Einbettungen ----------------------------------------------------------

async def test_einbettungen_kommen_als_vektoren_zurueck():
    """Die Vektoren, nicht die Huelle -- der Aufrufer will rechnen."""
    async with _client(_antwortet(EINBETTUNG)) as api:
        vektoren = await api.embeddings(["a", "b"], model="text-embedding-3-small")
    assert vektoren == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


async def test_ein_einzelner_text_ergibt_eine_liste_mit_einem_vektor():
    """Wie bei OpenAI selbst: input nimmt beides, data ist immer eine Liste.
    Ein wechselnder Rueckgabetyp zwaenge jeden Aufrufer zu einer Typpruefung."""
    einer = dict(EINBETTUNG, data=[EINBETTUNG["data"][0]])
    async with _client(_antwortet(einer)) as api:
        vektoren = await api.embeddings("nur einer", model="m")
    assert vektoren == [[0.1, 0.2, 0.3]]


async def test_einbettungen_gehen_an_die_richtige_route(aufrufe=None):
    aufrufe = []
    einer = dict(EINBETTUNG, data=[EINBETTUNG["data"][0]])
    async with _client(_antwortet(einer), aufrufe) as api:
        await api.embeddings("x", model="m", provider="openai")
    assert aufrufe[0].url.path.endswith("/api/v1/llm/openai/embeddings")


async def test_die_reihenfolge_der_vektoren_folgt_dem_index():
    """Die API darf umsortiert antworten; index ist die Zuordnung. Ohne
    Sortierung bekaeme der Aufrufer Vektoren zum falschen Text."""
    verdreht = dict(EINBETTUNG, data=list(reversed(EINBETTUNG["data"])))
    async with _client(_antwortet(verdreht)) as api:
        vektoren = await api.embeddings(["a", "b"], model="m")
    assert vektoren == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


# --- Moderation ------------------------------------------------------------

async def test_moderation_verdichtet_auf_geflaggt_und_warum():
    """Die Rohantwort fuehrt gut ein Dutzend Kategorien plus Punktwerte. Was
    ein Aufrufer entscheidet, ist: durchlassen oder nicht, und woran es lag."""
    async with _client(_antwortet(MODERATION)) as api:
        urteil = await api.moderate("etwas", model="omni-moderation-latest")
    assert isinstance(urteil, Moderation)
    assert urteil.flagged is True
    assert urteil.categories == ("violence",)
    assert urteil.scores["violence"] == 0.98
    assert urteil.raw is not None


async def test_unbeanstandeter_text_hat_keine_kategorien():
    sauber = {"id": "m", "model": "m", "results": [{
        "flagged": False,
        "categories": {"hate": False, "violence": False},
        "category_scores": {"hate": 0.0, "violence": 0.0}}]}
    async with _client(_antwortet(sauber)) as api:
        urteil = await api.moderate("harmlos", model="m")
    assert urteil.flagged is False
    assert urteil.categories == ()


async def test_moderation_ohne_ergebnis_ist_ein_fehler():
    """Eine leere results-Liste als 'nicht beanstandet' zu lesen waere die
    gefaehrlichste Auslegung -- dann liesse ein Ausfall alles durch."""
    async with _client(_antwortet({"id": "m", "model": "m", "results": []})) as api:
        with pytest.raises(EduSharingError, match="no result"):
            await api.moderate("etwas", model="m")


# --- Bilder ----------------------------------------------------------------

async def test_bilder_kommen_mit_url_oder_base64():
    """response_format entscheidet, was zurueckkommt. Beides in einem Feld zu
    mischen zwaenge den Aufrufer zum Raten."""
    async with _client(_antwortet(BILDER)) as api:
        bilder = await api.images("ein Baum", model="dall-e-3")
    assert [b.url for b in bilder] == ["https://beispiel.test/a.png", None]
    assert [b.b64 for b in bilder] == [None, "aGFsbG8="]
    assert bilder[0].revised_prompt == "ein Baum"


async def test_ein_bild_traegt_die_ganze_antwort_bei_sich():
    """``raw`` wie bei ``Moderation`` und ``Answer``.

    Beide Geschwister tragen den ganzen Antwortkoerper mit, auch wenn sie aus
    einem Unterobjekt gebaut sind -- ``Moderation`` aus ``results[0]``.
    ``GeneratedImage`` war das einzige der drei ohne, und hier wiegt das am
    meisten: ``quality``, ``size`` und ``usage`` stehen nur in dieser einen
    Antwort, und ein zweites Bild kostet wieder Geld. Gemessen am 21.09.2026
    waehlt ``quality="auto"`` selbst eine Stufe -- die Antwort ist die einzige
    Stelle, die sagt welche.
    """
    async with _client(_antwortet(BILD_GEMESSEN)) as api:
        bilder = await api.images("ein rotes Quadrat", model="gpt-image-1.5")
    assert len(bilder) == 1
    assert bilder[0].raw["quality"] == "low"
    assert bilder[0].raw["size"] == "1024x1024"
    assert bilder[0].raw["usage"]["total_tokens"] == 386


async def test_jedes_bild_nennt_seine_eigene_erzeugung():
    """``generation_id`` gehoert dem einzelnen Bild, nicht der Antwort.

    Ueber ``raw`` waere sie nur mit dem eigenen Listenindex zu finden, und den
    hat ein Aufrufer nicht in der Hand -- er haelt ein ``GeneratedImage``,
    keine Nummer. Deshalb ein eigenes Feld, wie schon bei ``revised_prompt``.
    """
    async with _client(_antwortet(BILD_GEMESSEN)) as api:
        bilder = await api.images("ein rotes Quadrat", model="gpt-image-1.5")
    assert bilder[0].generation_id == "75f3ab8b-be37-4268-b77b-75a062b29322"


async def test_was_kein_feld_dafuer_hat_bleibt_leer():
    """Die aeltere Form nennt keine ``generation_id`` -- das ist kein Fehler.

    ``dall-e-3`` schickt ``revised_prompt`` und keine Erzeugungsnummer, die
    GPT-Bildmodelle umgekehrt. Ein fehlendes Feld zu erfinden waere
    schlimmer als eine leere Zeichenkette.
    """
    async with _client(_antwortet(BILDER)) as api:
        bilder = await api.images("ein Baum", model="dall-e-3")
    assert [b.generation_id for b in bilder] == ["", ""]
    assert bilder[0].raw is bilder[1].raw, "derselbe Koerper, nicht zwei Kopien"


# --- Der generische Weg ----------------------------------------------------

async def test_call_erreicht_jede_durchgereichte_route():
    """Wie repo.raw fuer edu-sharing: was keine eigene Methode hat, ist
    trotzdem erreichbar -- 14 Routen bekommen keine dreizehn Wrapper."""
    aufrufe = []
    async with _client(_antwortet({"ok": True}), aufrufe) as api:
        antwort = await api.call("completions", {"model": "m", "prompt": "hi"})
    assert antwort == {"ok": True}
    assert aufrufe[0].url.path.endswith("/api/v1/llm/academiccloud/completions")


async def test_call_lehnt_einen_fuehrenden_schraegstrich_ab():
    """Sonst entstuende /api/v1/llm/anbieter//route, und der Fehler kaeme vom
    Server statt von hier."""
    async with _client(_antwortet({})) as api:
        with pytest.raises(ValidationError, match="without a leading"):
            await api.call("/audio/speech", {})


async def test_ein_fehler_der_route_wird_durchgereicht():
    async with _client(_antwortet({"message": "you must provide a model"}, 400)) as api:
        with pytest.raises(EduSharingError, match="model"):
            await api.embeddings("x", model="")


# --- Die Route ist eine Vertrauensgrenze -----------------------------------

@pytest.mark.parametrize("route", [
    "embeddings",
    "chat/completions",
    "images/generations",
    "fine_tuning/jobs",
    "vector_stores",
])
async def test_echte_routen_gehen_durch(route):
    aufrufe = []
    async with _client(_antwortet({"ok": True}), aufrufe) as api:
        await api.call(route, {})
    assert aufrufe[0].url.path.endswith(f"/api/v1/llm/academiccloud/{route}")


@pytest.mark.parametrize("route", [
    "../../administration/account",   # verlaesst /api/v1/llm/ voellig
    "..",
    "a/../../b",
    "/embeddings",                    # fuehrender Schraegstrich
    "embeddings/",                    # leeres Segment am Ende
    "a//b",                           # leeres Segment in der Mitte
    "embeddings?admin=1",             # eingeschmuggelte Anfrageparameter
    "embeddings#x",
    "embeddings account",
    # ``$`` matcht auch **vor** einem abschliessenden Zeilenumbruch, also
    # liess ``.match`` das hier durch -- ein Umbruch im Pfad einer Adresse
    # (Pruefung 08.09.2026, gefunden an derselben Bauform in content.py).
    "embeddings\n",
    "",
])
async def test_eine_route_darf_ihren_pfad_nicht_verlassen(route):
    """Gemessen am 28.08.2026, bevor das hier stand:

        call("../../administration/account")
        -> https://…/api/v1/administration/account

    Die Anfrage verliess /api/v1/llm/{provider}/, erreichte die
    Administrations-API und nahm den X-API-KEY mit. ``path_segment`` wurde auf
    den Anbieter angewandt, auf die Route nicht -- in derselben Zeile.

    Das zaehlt hier besonders: diese Bibliothek ist fuer KI-Anwendungen gebaut,
    und ``call`` ist die Methode, deren Argument ein Modell waehlt. Genau der
    Fall, den der Docstring von ``path_segment`` als Grund seiner Existenz
    nennt.
    """
    versendet = []
    async with _client(_antwortet({"ok": True}), versendet) as api:
        with pytest.raises(ValidationError):
            await api.call(route, {})
    assert not versendet, (
        f"{route!r} wurde abgesetzt: {versendet[0].url if versendet else ''}")


# --- responses -------------------------------------------------------------
#
# Gemessen am 31.08.2026: **beide** Anbieter koennen den Endpunkt.
#
#   openai/gpt-5.6-luna     status=completed   'Hallo!'
#   academiccloud/gemma-4   status=completed   'Hallo! Wie kann ich dir...'
#   academiccloud/qwen3.5   status=incomplete  Budget ins Denken gelaufen
#
# Die Parameterform ist eine andere als bei chat/completions -- dort
# ``reasoning_effort``, hier ``reasoning={"effort": ...}``. Die chat-Form wird
# ausdruecklich abgelehnt: "Unsupported parameter: 'reasoning_effort'. In the
# Responses API, ...". ``model`` ist Pflicht, es gibt keine automatische Wahl.

ANTWORT_FERTIG = {
    "status": "completed",
    "model": "gpt-5.6-luna",
    "output": [{"content": [{"type": "output_text", "text": "Hallo!"}]}],
    "usage": {"output_tokens": 6},
}

ANTWORT_ABGESCHNITTEN = {
    "status": "incomplete",
    "model": "qwen3.5-122b-a10b",
    "incomplete_details": {"reason": "max_output_tokens"},
    "output": [{"content": [{"type": "output_text", "text": "Thinking Proce"}]}],
    "usage": {"output_tokens": 64},
}


async def test_responses_liefert_den_text():
    async with _client(lambda r: httpx.Response(200, json=ANTWORT_FERTIG)) as api:
        antwort = await api.respond("Sag hallo.", model="gpt-5.6-luna")
    assert antwort.text == "Hallo!"
    assert antwort.status == "completed"
    assert antwort.truncated is False
    assert antwort.model == "gpt-5.6-luna"


async def test_eine_abgeschnittene_antwort_sagt_dass_sie_es_ist():
    """Der Punkt der ganzen Klasse.

    ``incomplete`` heisst, das Budget ist ins Denken gelaufen und der Text ist
    abgeschnitten. Nur den Text zurueckzugeben saehe aus wie eine vollstaendige
    Antwort -- und genau davor schuetzt diese Bibliothek sonst ueberall.
    """
    async with _client(lambda r: httpx.Response(200, json=ANTWORT_ABGESCHNITTEN)) as api:
        antwort = await api.respond("x", model="qwen3.5-122b-a10b")
    assert antwort.truncated is True
    assert antwort.reason == "max_output_tokens"
    assert antwort.text == "Thinking Proce"


async def test_ein_leerer_modellname_ist_ein_fehler():
    """``None`` heisst "waehle du", ``""`` heisst nichts.

    Seit respond die Politik von chat teilt, ist eine Wahl durch die
    Bibliothek keine stille mehr -- sie folgt derselben gemessenen Rangfolge.
    Ein leerer String ist aber keine Bitte darum, sondern ein Aufrufer, dem
    seine Variable abhandengekommen ist. Den still zu einer Modellwahl zu
    machen, verstuende ihn falsch.
    """
    async with _client(lambda r: httpx.Response(200, json=ANTWORT_FERTIG)) as api:
        with pytest.raises(EduSharingError):
            await api.respond("x", model="")


#: Zwei Modelle, rangfaehig: demand und Ausgabetyp sind da.
_MODELLE = {"data": [
    {"id": "erst-das", "demand": 0, "status": "ready",
     "input": ["text"], "output": ["text"]},
    {"id": "dann-das", "demand": 1, "status": "ready",
     "input": ["text"], "output": ["text"]},
]}


async def test_responses_weicht_auf_den_naechsten_kandidaten_aus():
    """Dieselbe Falle wie bei chat, jetzt mit demselben Schutz.

    Gemessen am 21.09.2026: das Gateway fuehrt Modelle, die es nicht bedient,
    und die Liste sagt es nicht vorher -- ``apertus-70b-instruct-2509`` meldet
    ``ready`` und Auslastung 0 und antwortet mit 503. Wer eine Aufzaehlung
    uebergibt, will eine Antwort, nicht die Nachricht, dass ausgerechnet der
    erste Kandidat nicht abrechenbar ist.
    """
    versuche = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=_MODELLE)
        import json as _json
        mid = _json.loads(request.content)["model"]
        versuche.append(mid)
        if mid == "erst-das":
            return httpx.Response(503, json={"message":
                "Model pricing unavailable for 'erst-das' - cannot enforce cost quota"})
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        antwort = await api.respond("x", model=["erst-das", "dann-das"])
    assert antwort.text == "Hallo!"
    assert versuche == ["erst-das", "dann-das"], versuche


async def test_responses_ohne_modell_waehlt_wie_chat():
    """``model=None`` ueberlaesst der Bibliothek die Wahl -- nach derselben
    Rangfolge wie ``chat``: am wenigsten ausgelastet zuerst."""
    versuche = []

    def handler(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=_MODELLE)
        import json as _json
        versuche.append(_json.loads(request.content)["model"])
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        antwort = await api.respond("x")
    assert antwort.text == "Hallo!"
    assert versuche == ["erst-das"], versuche


async def test_ein_genannter_modellname_fragt_keine_liste_ab():
    """Wer eines nennt, loest keine Erkundung aus -- eine Anfrage, nicht zwei."""
    pfade = []

    def handler(request):
        pfade.append(request.url.path)
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        await api.respond("x", model="gpt-5.6-luna")
    assert all(not p.endswith("/models") for p in pfade), pfade


async def test_die_vorgabe_kommt_in_der_responses_form():
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        await api.respond("x", model="gpt-5.6-luna")
    import json as _json
    koerper = _json.loads(aufrufe[-1].content)
    assert koerper["reasoning"] == {"effort": "low"}
    assert koerper["text"] == {"verbosity": "low"}
    assert "reasoning_effort" not in koerper


async def test_ohne_faehiges_modell_entfaellt_die_vorgabe():
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        await api.respond("x", model="gemma-4-31b-it")
    import json as _json
    koerper = _json.loads(aufrufe[-1].content)
    assert "reasoning" not in koerper
    assert "text" not in koerper


async def test_ausdruecklicher_wunsch_wird_auch_hier_nicht_verworfen():
    async with _client(lambda r: httpx.Response(200, json=ANTWORT_FERTIG)) as api:
        with pytest.raises(ValidationError) as info:
            await api.respond("x", model="gemma-4-31b-it", reasoning_effort="high")
    assert "gemma-4-31b-it" in str(info.value)


# --- Fremddaten am Rand ----------------------------------------------------

@pytest.mark.parametrize("rumpf, erwartet", [
    ({"output": [{"content": [{"text": "ok"}]}]}, "ok"),
    ({"output": ["Text statt eines Eintrags"]}, ""),
    ({"output": [{"content": "kein dict"}]}, ""),
    ({"output": [{}]}, ""),
    ({"output": None}, ""),
    ({}, ""),
])
def test_der_text_wird_auch_aus_unerwarteten_ruempfen_gelesen(rumpf, erwartet):
    """Der Rumpf kommt vom Gateway, nicht von uns.

    Ein ``AttributeError`` waere hier weder aussagekraeftig noch als
    ``EduSharingError`` fangbar -- die Bibliothek ist an genau solchen Raendern
    sonst vorsichtig (``Model.is_retired_on`` faengt das unlesbare Datum,
    ``read_answer`` prueft auf leere ``choices``).
    """
    from edusharing.bapi.passthrough import _text_of
    assert _text_of(rumpf) == erwartet


async def test_zwei_wege_denselben_wert_zu_setzen_sind_ein_fehler():
    """``extra`` ist die Notluke -- aber nicht, um denselben Wert zweimal zu setzen.

    Frueher gewann ``extra`` stillschweigend, weil es zuletzt ausgebreitet
    wurde: ``reasoning_effort="high"`` verschwand neben einem eigenen
    ``reasoning``. Das ist genau die stille Verwerfung, gegen die diese
    Parameter ueberhaupt so behandelt werden.
    """
    async with _client(lambda r: httpx.Response(200, json=ANTWORT_FERTIG)) as api:
        with pytest.raises(ValidationError) as info:
            await api.respond("x", model="gpt-5.6-luna", reasoning_effort="high",
                              reasoning={"effort": "minimal"})
    assert "reasoning" in str(info.value)


async def test_wer_nur_extra_setzt_bekommt_es_und_nicht_die_vorgabe():
    """Umgekehrt darf die Vorgabe einen eigenen Wert nicht ueberschreiben."""
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        return httpx.Response(200, json=ANTWORT_FERTIG)

    async with _client(handler) as api:
        await api.respond("x", model="gpt-5.6-luna",
                          reasoning={"effort": "minimal"})
    import json as _json
    koerper = _json.loads(aufrufe[-1].content)
    assert koerper["reasoning"] == {"effort": "minimal"}
    # Die Vorgabe fuer verbosity bleibt, die kollidiert ja nicht.
    assert koerper["text"] == {"verbosity": "low"}


# --- Die Routen mit einer Datei -------------------------------------------
#
# Vier der weitergeleiteten Routen nehmen eine Datei statt eines JSON-Koerpers:
# audio/transcriptions, audio/translations, images/edits und files. ``call``
# erreichte keine davon -- nicht, weil das Gateway sie verweigert haette,
# sondern weil die Bibliothek nur JSON senden konnte.


async def test_call_multipart_schickt_datei_und_felder():
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        return httpx.Response(200, json={"text": "Test."})

    async with _client(handler) as api:
        antwort = await api.call_multipart(
            "audio/transcriptions", {"model": "gpt-4o-mini-transcribe"},
            file=b"ID3 nicht wirklich mp3", filename="probe.mp3",
            content_type="audio/mpeg", provider="openai")

    assert antwort["text"] == "Test."
    anfrage = aufrufe[0]
    assert anfrage.url.path.endswith("/openai/audio/transcriptions"), anfrage.url
    assert anfrage.headers["content-type"].startswith("multipart/form-data")
    koerper = anfrage.content
    assert b'name="file"; filename="probe.mp3"' in koerper, koerper[:200]
    assert b"audio/mpeg" in koerper
    assert b'name="model"' in koerper
    assert b"gpt-4o-mini-transcribe" in koerper


async def test_der_feldname_der_datei_ist_waehlbar():
    """``images/edits`` nennt sie ``image``, die Audio-Routen ``file`` --
    die Route entscheidet, nicht die Bibliothek."""
    aufrufe = []

    def handler(request):
        aufrufe.append(request)
        return httpx.Response(200, json={"data": []})

    async with _client(handler) as api:
        await api.call_multipart(
            "images/edits", {"model": "gpt-image-1", "prompt": "heller"},
            file=b"PNG", filename="bild.png", field="image", provider="openai")

    koerper = aufrufe[0].content
    assert b'name="image"; filename="bild.png"' in koerper, koerper[:200]
    assert b'name="prompt"' in koerper


async def test_ohne_inhaltstyp_wird_er_nicht_erfunden():
    """httpx raet dann selbst anhand des Namens -- was die Bibliothek nicht
    besser kann und darum nicht vortaeuschen soll."""
    aufrufe = []

    async with _client(lambda r: (aufrufe.append(r),
                                  httpx.Response(200, json={"ok": True}))[1]) as api:
        await api.call_multipart("files", {"purpose": "assistants"},
                                 file=b"x", filename="notiz.txt", provider="openai")
    assert b'filename="notiz.txt"' in aufrufe[0].content


async def test_eine_unsichere_route_wird_auch_hier_abgelehnt():
    """Dieselbe Pruefung wie bei ``call`` -- der Weg mit der Datei ist kein
    Loch neben der Tuer."""
    async with _client(lambda r: httpx.Response(200, json={})) as api:
        with pytest.raises(ValidationError):
            await api.call_multipart("../secrets", {}, file=b"x",
                                     filename="a.txt", provider="openai")


@pytest.mark.parametrize("inhaltstyp", [
    "audio/mpeg\r\nX-Injected: yes", "audio/mpeg\n", "audio/mpeg; charset=utf-8", "",
])
async def test_ein_inhaltstyp_der_eine_kopfzeile_faelscht_wird_abgelehnt(inhaltstyp):
    """Audit SEC-23-3 (23.09.2026): httpx schreibt den Inhaltstyp eines
    Multipart-Teils unmaskiert in dessen Kopf (SEC-7, gemessen 08.09.2026).
    ``content.upload`` prueft ihn seitdem, ``call_multipart`` vom 21.09. nicht:
    gemessen, ``"audio/mpeg\\r\\nX-Injected: yes"`` schrieb eine eigene Zeile in
    den Koerper. Abgelehnt wird, bevor etwas gesendet ist -- und die Meldung
    nennt das Argument so, wie der Aufrufer es geschrieben hat."""
    aufrufe = []
    async with _client(_antwortet({"text": "x"}), aufrufe) as api:
        with pytest.raises(ValidationError, match="content_type"):
            await api.call_multipart("audio/transcriptions", {"model": "m"},
                                     file=b"x", filename="a.mp3",
                                     content_type=inhaltstyp, provider="openai")
    assert aufrufe == []
