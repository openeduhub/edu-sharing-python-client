"""Der Template-Modus der b-api -- serverseitige Prompts unter
``/api/v1/edu-sharing/*``.

Der zweite Betriebsmodus neben dem Proxy (``BildungsAPI``). Dort schickt der
Client den Prompt; hier liegt er im Metadatenset, und der Client schickt nur,
**welche** Konfiguration, **welcher** Kontext-Knoten und **welche** Werte.

Gemessen am 11.09.2026 gegen Staging, und jede Zeile hier beruht darauf:

* **Alle fuenf Felder sind Pflicht** -- ``metadataSet``, ``configIds``,
  ``user``, ``contextNodeId``, ``variables`` (auch leer). Fehlt eines: 400.
* ``/limited`` nimmt als ``variables`` nur ``[{widgetId, valueId}]``; eine Map
  scheitert beim Deserialisieren.
* Eine unbekannte Konfigurations-ID antwortet **500**
  ``Missing MDS AI configuration for id ...`` -- ein Aufruferfehler mit dem
  Status eines Serverfehlers.
* Jeder Fehlerkoerper traegt einen Java-Stacktrace von rund 18 KB unter
  ``trace``.
* ``/suggestions`` legt edu-sharing-Vorschlaege an: ein zweiter Versuch nach
  einer Antwort, die nicht ankam, legt sie womoeglich ein zweites Mal an.
"""

import json

import httpx
import pytest

from edusharing.bapi import BapiTemplates, NodeConfig

GATEWAY = "https://gateway.example.test"
PFAD = "/api/v1/edu-sharing"
KNOTEN = "7eb4a7c2-299b-4020-8667-89187f6a8dff"
COMPLETION = {
    "id": "chatcmpl-1", "object": "chat.completion", "model": "gpt-4.1-mini",
    "choices": [{"index": 0, "message": {"role": "assistant",
                                          "content": "Die Luft besteht aus Gasen."}}],
}


def _vorlagen(handler, aufrufe=None, **kwargs):
    def wrapped(request):
        if aufrufe is not None:
            aufrufe.append(request)
        return handler(request)

    kwargs.setdefault("api_key", "geheimer-schluessel")
    kwargs.setdefault("base_url", GATEWAY)
    kwargs.setdefault("metadataset", "mds_oeh")
    kwargs.setdefault("backoff_base", 0.0)
    return BapiTemplates(
        client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), **kwargs)


def _antwortet(nutzlast, status=200):
    return lambda _request: httpx.Response(status, json=nutzlast)


def _koerper(request: httpx.Request) -> dict:
    return json.loads(request.content)


# --- Aufgabe 3: die kleinste durchgehende Scheibe --------------------------

async def test_chat_schickt_genau_die_fuenf_pflichtfelder():
    """Gemessen: fehlt eines, antwortet der Server 400. Also gehen alle fuenf
    mit -- auch ``variables``, wenn es nichts einzusetzen gibt."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert set(_koerper(aufrufe[0])) == {
        "metadataSet", "configIds", "user", "contextNodeId", "variables"}


async def test_ein_string_ist_eine_konfiguration_aus_dem_metadatenset():
    """Die haeufige Form: alle 22 gemessenen Konfigurationen liegen im
    Metadatenset."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(["topic_page_ai_default"], context_node_id=KNOTEN)
    assert _koerper(aufrufe[0])["configIds"] == [
        {"type": "mds", "id": "topic_page_ai_default"}]


async def test_eine_knotenkonfiguration_nennt_knoten_und_namen():
    """Die zweite Form: die Konfiguration steht in ``ccm:bapi_config`` eines
    Knotens, unter einem Namen."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat([NodeConfig("knoten-1", "defaults")], context_node_id=KNOTEN)
    assert _koerper(aufrufe[0])["configIds"] == [
        {"type": "node", "nodeId": "knoten-1", "configName": "defaults"}]


async def test_die_reihenfolge_der_konfigurationen_bleibt():
    """Die Spec: jede spaetere Konfiguration hat Vorrang vor der frueheren. Die
    Reihenfolge ist also Bedeutung, nicht Zufall -- gemessen setzt die Kette
    [default, chat_completion, header_description] Provider, Modell und
    Nachricht in genau dieser Folge zusammen."""
    aufrufe = []
    kette = ["topic_page_ai_default", NodeConfig("k", "spezial"), "zuletzt"]
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(kette, context_node_id=KNOTEN)
    ids = [c.get("id") or c.get("configName") for c in _koerper(aufrufe[0])["configIds"]]
    assert ids == ["topic_page_ai_default", "spezial", "zuletzt"]


async def test_ein_einzelner_variablenwert_wird_zur_liste():
    """Der Server erwartet ``{schluessel: [werte]}``. Ein einzelner String ist
    der haeufige Fall und wird eingewickelt; eine Liste bleibt, was sie ist."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(["a"], context_node_id=KNOTEN,
                            variables={"cm:name": "Vulkane", "keywords": ["a", "b"]})
    assert _koerper(aufrufe[0])["variables"] == {
        "cm:name": ["Vulkane"], "keywords": ["a", "b"]}


async def test_ohne_variablen_geht_ein_leeres_objekt_mit():
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert _koerper(aufrufe[0])["variables"] == {}


async def test_ohne_angabe_ist_der_nutzer_guest():
    """Der Server verlangt das Feld fuer Nutzer-Platzhalter; gemessen nutzt
    keine der 22 Konfigurationen einen, und ``guest`` hat funktioniert."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert _koerper(aufrufe[0])["user"] == "guest"


async def test_chat_trifft_pfad_schluessel_und_metadatenset():
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe, metadataset="mds_x") as vorlagen:
        await vorlagen.chat(["a"], context_node_id=KNOTEN)
    anfrage = aufrufe[0]
    assert anfrage.method == "POST"
    assert anfrage.url.path == f"{PFAD}/chat/completion"
    assert anfrage.headers["X-API-KEY"] == "geheimer-schluessel"
    assert _koerper(anfrage)["metadataSet"] == "mds_x"
    assert _koerper(anfrage)["contextNodeId"] == KNOTEN


async def test_chat_liefert_den_text_der_antwort():
    """Wie ``BildungsAPI.chat``: der Text, gelesen mit demselben ``read_answer``."""
    async with _vorlagen(_antwortet(COMPLETION)) as vorlagen:
        text = await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert text == "Die Luft besteht aus Gasen."


# --- Aufgabe 4: gepruefte Eingaben, bevor etwas gesendet wird -------------
#
# Der Server wuesste es auch -- aber seine Meldung nennt das fehlende Feld
# erst hinter 150 Zeichen Java-Klassenname, und der Weg dorthin kostet einen
# Aufruf. Gemessen: "Parameter specified as non-null is null: method
# org.edusharing...EduSharingLlmRequest.<init>, parameter contextNodeId".

@pytest.mark.parametrize(("aufruf", "wort"), [
    ({"configs": [], "context_node_id": KNOTEN}, "configuration"),
    ({"configs": ["a"], "context_node_id": ""}, "context_node_id"),
    ({"configs": ["a"], "context_node_id": KNOTEN, "user": ""}, "user"),
    ({"configs": [""], "context_node_id": KNOTEN}, "configuration"),
    ({"configs": [NodeConfig("", "x")], "context_node_id": KNOTEN}, "configuration"),
    ({"configs": ["a"], "context_node_id": KNOTEN, "variables": {"k": 3}}, "k"),
    ({"configs": ["a"], "context_node_id": KNOTEN, "variables": {"k": ["a", 3]}}, "k"),
])
async def test_ungueltiges_wird_vor_dem_senden_abgewiesen(aufruf, wort):
    from edusharing.errors import ValidationError
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        with pytest.raises(ValidationError, match=wort):
            await vorlagen.chat(aufruf.pop("configs"), **aufruf)
    assert aufrufe == [], "nichts darf das Haus verlassen"


async def test_ein_einzelner_string_statt_einer_liste_wird_abgewiesen():
    """``chat("abc")`` waere in Python eine Folge von drei Konfigurationen
    ``a``, ``b``, ``c`` -- ein stiller Fehler, der drei unbekannte IDs schickt."""
    from edusharing.errors import ValidationError
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        with pytest.raises(ValidationError, match="list"):
            await vorlagen.chat("topic_page_ai_default", context_node_id=KNOTEN)
    assert aufrufe == []


# --- Aufgabe 5: Fehler und Wiederholungen ----------------------------------
#
# Der Grund, warum der Template-Modus nicht den Anfrageweg des Proxys leiht:
# der wiederholt 500, und 500 ist hier -- gemessen -- der Code fuer eine
# falsche Konfigurations-ID. Dreimal nachfragen, ob es sie inzwischen gibt,
# kostet nur Zeit und sagt dem Aufrufer nichts.

def _spring_fehler(status, meldung, fehler="Bad Request"):
    """Die gemessene Form eines Fehlerkoerpers, samt Stacktrace."""
    return {"timestamp": "2026-09-11T10:42:40.977Z", "status": status,
            "error": fehler, "message": meldung, "path": f"{PFAD}/chat/completion",
            "trace": "java.lang.IllegalStateException: GEHEIMER_STACKTRACE\n\tat org."
                     + "x" * 18000}


def _folge(*antworten):
    """Antwortet der Reihe nach; die letzte wiederholt sich."""
    stapel = list(antworten)

    def handler(_request):
        status, nutzlast = stapel.pop(0) if len(stapel) > 1 else stapel[0]
        return httpx.Response(status, json=nutzlast)
    return handler


async def test_eine_400_wird_zum_validierungsfehler_mit_der_servermeldung():
    from edusharing.errors import ValidationError
    aufrufe = []
    handler = _antwortet(_spring_fehler(400, "JSON parse error: kaputt"), 400)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(ValidationError, match="JSON parse error"):
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert len(aufrufe) == 1


async def test_eine_unbekannte_konfiguration_ist_ein_aufruferfehler_ohne_wiederholung():
    """Gemessen: 500 ``Missing MDS AI configuration for id ...``. Der Status
    luegt; die Meldung nicht. Kein zweiter Versuch -- die ID wird nicht
    richtiger."""
    from edusharing.errors import ValidationError
    aufrufe = []
    handler = _antwortet(_spring_fehler(
        500, "Missing MDS AI configuration for id gibt_es_nicht", "Internal Server Error"), 500)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(ValidationError) as fehler:
            await vorlagen.chat(["gibt_es_nicht"], context_node_id=KNOTEN)
    assert len(aufrufe) == 1
    assert "gibt_es_nicht" in str(fehler.value)
    assert "mds_oeh" in str(fehler.value), "das Metadatenset gehoert zur Antwort"


async def test_eine_andere_500_wird_nicht_wiederholt():
    """500 traegt hier Konfigurationsfehler; eine Wiederholung kostet
    Wartezeit und aendert nichts."""
    from edusharing.errors import ServerError
    aufrufe = []
    handler = _antwortet(_spring_fehler(500, "NullPointerException", "Internal Server Error"), 500)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(ServerError):
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert len(aufrufe) == 1


async def test_eine_503_wird_wiederholt_und_der_zweite_versuch_zaehlt():
    """Ueberlastet heisst: nichts geschah. ``chat`` schreibt nichts, ein
    zweiter Versuch kostet hoechstens Tokens."""
    aufrufe = []
    handler = _folge((503, {"message": "busy"}), (200, COMPLETION))
    async with _vorlagen(handler, aufrufe) as vorlagen:
        text = await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert text == "Die Luft besteht aus Gasen."
    assert len(aufrufe) == 2


async def test_ein_unbepreistes_modell_wird_auch_hier_nicht_wiederholt():
    """Dasselbe Gateway, dieselbe Antwort, dieselbe Regel.

    Gemessen wurde der Fall am LLM-Weg (siehe ``test_bapi_client``); die Regel
    gehoert aber dem Gateway, nicht einer der beiden Klassen. Stuende sie nur
    dort, haette dieselbe Pruefung wieder zwei Faelle und eine Kopie -- genau
    der Befund ARC-20-1.
    """
    from edusharing.errors import EduSharingError

    aufrufe = []
    handler = _antwortet({"message": "Model pricing unavailable for 'x' "
                                     "- cannot enforce cost quota"}, 503)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(EduSharingError):
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert len(aufrufe) == 1


async def test_eine_verbindungsstoerung_wird_bei_chat_wiederholt():
    aufrufe = []
    versuche = iter([httpx.ConnectError("weg"), None])

    def handler(request):
        fehler = next(versuche)
        if fehler:
            raise fehler
        return httpx.Response(200, json=COMPLETION)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        assert await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert len(aufrufe) == 2


async def test_der_stacktrace_landet_nie_in_einer_meldung():
    """18 KB Java-Interna je Fehler, gemessen. Sie in eine Ausnahme zu kippen
    hiesse, sie in jedes Protokoll zu kippen, das Ausnahmen schreibt."""
    from edusharing.errors import EduSharingError
    for status in (400, 401, 500, 503):
        handler = _antwortet(_spring_fehler(status, "etwas ging schief"), status)
        async with _vorlagen(handler, max_retries=0) as vorlagen:
            with pytest.raises(EduSharingError) as fehler:
                await vorlagen.chat(["a"], context_node_id=KNOTEN)
        assert "GEHEIMER_STACKTRACE" not in str(fehler.value), status
        assert len(str(fehler.value)) < 600, status


async def test_ohne_meldung_hilft_das_feld_error():
    from edusharing.errors import AuthenticationError
    handler = _antwortet({"status": 401, "error": "Unauthorized", "trace": "x"}, 401)
    async with _vorlagen(handler) as vorlagen:
        with pytest.raises(AuthenticationError, match="Unauthorized"):
            await vorlagen.chat(["a"], context_node_id=KNOTEN)


async def test_eine_403_sagt_wessen_rechte_fehlen():
    """Gemessen am 11.09.2026: das Gateway liest den Kontext-Knoten mit seinem
    **eigenen** Konto. Ein privater Knoten antwortete 403 -- mit ``user`` gleich
    ``guest`` und mit dem Konto, dem der Knoten gehoert, gleichermassen. Die
    Meldung des Servers sagt "Sie verfuegen nicht ueber die Berechtigungen",
    und wer sie liest, prueft seine eigenen Rechte. Die Meldung muss sagen,
    dass es um die des Gateways geht."""
    from edusharing.errors import PermissionDeniedError
    aufrufe = []
    handler = _antwortet(_spring_fehler(
        403, "org.alfresco.repo.security.permissions.AccessDeniedException: "
             "0811495684 Zugriff verweigert.", "Forbidden"), 403)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(PermissionDeniedError) as fehler:
            await vorlagen.chat(["a"], context_node_id=KNOTEN, user="jemand")
    assert "Zugriff verweigert" in str(fehler.value)
    assert "own account" in str(fehler.value)
    assert len(aufrufe) == 1


async def test_der_hinweis_gilt_auch_fuer_das_fehlende_schreibrecht():
    """Die zweite gemessene Ablehnung des Repositoriums: ``qas`` ohne Write."""
    from edusharing.errors import PermissionDeniedError
    handler = _antwortet(_spring_fehler(
        403, "org.edu_sharing.service.InsufficientPermissionException: nodeId with "
             "id n-1 requires permission(s): Write", "Forbidden"), 403)
    async with _vorlagen(handler) as vorlagen:
        with pytest.raises(PermissionDeniedError) as fehler:
            await vorlagen.qas(["n-1"])
    assert "own account" in str(fehler.value)


async def test_eine_403_ohne_ablehnung_des_repositoriums_bekommt_keinen_hinweis():
    """Review 11.09.2026: das Gateway antwortet auch selbst mit 403 -- gemessen
    fuer Routen, die es nicht durchreicht. Dort waere "pruef die Rechte am
    Knoten" die falsche Spur."""
    from edusharing.errors import PermissionDeniedError
    handler = _antwortet({"timestamp": "2026-09-11T10:42:40.977Z", "status": 403,
                          "error": "Forbidden", "message": "Access Denied",
                          "path": f"{PFAD}/chat/completion"}, 403)
    async with _vorlagen(handler) as vorlagen:
        with pytest.raises(PermissionDeniedError) as fehler:
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert "Access Denied" in str(fehler.value)
    assert "own account" not in str(fehler.value)


async def test_die_ablehnung_des_anbieters_liest_sich_als_satz():
    """Gemessen am 11.09.2026: lehnt der Anbieter ab, reicht die b-api seinen
    Fehler durch -- ``{"error": {"message": ..., "type": ...}}``, ohne
    ``message`` obenauf. So kam es: ``respond`` mit einer chat-Konfiguration.
    In der Meldung soll der Satz stehen, nicht die Python-Darstellung des
    Objekts drumherum."""
    from edusharing.errors import ValidationError
    satz = ("Unsupported parameter: 'messages'. In the Responses API, this "
            "parameter has moved to 'input'.")
    handler = _antwortet({"error": {"message": satz, "type": "invalid_request_error",
                                    "param": "messages", "code": None}}, 400)
    async with _vorlagen(handler) as vorlagen:
        with pytest.raises(ValidationError) as fehler:
            await vorlagen.respond(["a"], context_node_id=KNOTEN)
    assert satz in str(fehler.value)
    assert "invalid_request_error" not in str(fehler.value)


# --- Aufgabe 6: der Limited-Modus ------------------------------------------
#
# Gemessen: ``/limited`` nimmt als ``variables`` nur ``[{widgetId, valueId}]``,
# eine Map scheitert. Freier Text fuer ``cm:name`` erreichte den Prompt nicht
# (11.09.2026); eingesetzt wird laut Spec die Beschriftung des gewaehlten Werts.
# Deshalb heisst der Parameter hier ``choices``, nicht ``variables``: der
# Unterschied soll im Aufruf stehen.

LRT = "ccm:educationallearningresourcetype"
APPLICATION = "http://w3id.org/openeduhub/vocabs/learningResourceType/application"


async def test_limited_schickt_widget_und_wert_paare():
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat_limited(["a"], context_node_id=KNOTEN,
                                    choices={LRT: APPLICATION})
    anfrage = aufrufe[0]
    assert anfrage.url.path == f"{PFAD}/chat/completion/limited"
    assert _koerper(anfrage)["variables"] == [{"widgetId": LRT, "valueId": APPLICATION}]


async def test_mehrere_werte_werden_zu_mehreren_paaren():
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat_limited(["a"], context_node_id=KNOTEN,
                                    choices={"w1": ["v1", "v2"], "w2": "v3"})
    assert _koerper(aufrufe[0])["variables"] == [
        {"widgetId": "w1", "valueId": "v1"}, {"widgetId": "w1", "valueId": "v2"},
        {"widgetId": "w2", "valueId": "v3"}]


async def test_limited_ohne_auswahl_schickt_eine_leere_liste():
    """Eine Konfiguration, die nur ``node(...)`` liest, braucht keine Auswahl
    -- das Feld muss trotzdem mit."""
    aufrufe = []
    async with _vorlagen(_antwortet(COMPLETION), aufrufe) as vorlagen:
        await vorlagen.chat_limited(["a"], context_node_id=KNOTEN)
    assert _koerper(aufrufe[0])["variables"] == []


def test_limited_nimmt_keinen_freitext_an():
    """Die Signatur selbst: wer ``variables=`` an eine Limited-Methode gibt,
    bekommt einen TypeError, keinen still verworfenen Freitext."""
    import inspect
    for name in ("chat_limited", "respond_limited", "images_limited"):
        parameter = inspect.signature(getattr(BapiTemplates, name)).parameters
        assert "variables" not in parameter, name
        assert "choices" in parameter, name


# --- Aufgabe 7: respond und images, je auch limited -------------------------

ANTWORT = {"id": "resp-1", "object": "response", "model": "gpt-4.1-mini",
           "status": "completed",
           "output": [{"type": "message", "content": [
               {"type": "output_text", "text": "Vulkane entstehen an Plattengrenzen."}]}]}
BILDER = {"created": 1, "data": [
    {"url": "https://bilder.example.test/1.png", "revised_prompt": "ein Baum"},
    {"b64_json": "aGFsbG8="}]}


@pytest.mark.parametrize(("methode", "pfad", "nutzlast", "art"), [
    ("respond", "/responses", ANTWORT, {}),
    ("respond_limited", "/responses/limited", ANTWORT, {"choices": {}}),
    ("images", "/images/generations", BILDER, {}),
    ("images_limited", "/images/generations/limited", BILDER, {"choices": {}}),
])
async def test_jede_route_trifft_ihren_pfad(methode, pfad, nutzlast, art):
    aufrufe = []
    async with _vorlagen(_antwortet(nutzlast), aufrufe) as vorlagen:
        await getattr(vorlagen, methode)(["a"], context_node_id=KNOTEN, **art)
    assert aufrufe[0].url.path == f"{PFAD}{pfad}"


async def test_respond_liefert_eine_answer_wie_der_proxy():
    """Derselbe Parser wie ``BildungsAPI.respond`` -- auch ``truncated``."""
    from edusharing.bapi import Answer
    async with _vorlagen(_antwortet(ANTWORT)) as vorlagen:
        antwort = await vorlagen.respond(["a"], context_node_id=KNOTEN)
    assert isinstance(antwort, Answer)
    assert antwort.text == "Vulkane entstehen an Plattengrenzen."
    assert antwort.truncated is False


async def test_images_liefert_generierte_bilder_wie_der_proxy():
    """Derselbe Parser wie ``BildungsAPI.images`` -- samt ``raw``.

    Der Vorlagenmodus teilt sich ``_images_from`` mit dem Proxy, also erbt er
    jedes Feld, das dort dazukommt. Am 21.09.2026 kam ``raw`` dazu, und dieser
    Test hat es gemeldet, weil er die Objekte **ganz** vergleicht. Genau dafuer
    steht der Ganzvergleich hier: ein Feld, das der Vorlagenmodus stillschweigend
    nicht mehr fuellt, faellt sonst niemandem auf.
    """
    from edusharing.bapi import GeneratedImage
    async with _vorlagen(_antwortet(BILDER)) as vorlagen:
        bilder = await vorlagen.images(["a"], context_node_id=KNOTEN)
    assert bilder == [
        GeneratedImage(url="https://bilder.example.test/1.png",
                       revised_prompt="ein Baum", raw=BILDER),
        GeneratedImage(b64="aGFsbG8=", raw=BILDER)]


#: Die sechs lesenden Routen: Methode, Route, was sie zusaetzlich braucht.
LESENDE_ROUTEN = [
    ("chat", "chat/completion", {}),
    ("chat_limited", "chat/completion/limited", {"choices": {}}),
    ("respond", "responses", {}),
    ("respond_limited", "responses/limited", {"choices": {}}),
    ("images", "images/generations", {}),
    ("images_limited", "images/generations/limited", {"choices": {}}),
]


@pytest.mark.parametrize("koerper", [b"[]", b'"ok"', b"null"])
@pytest.mark.parametrize(("methode", "route", "art"), LESENDE_ROUTEN)
async def test_eine_antwort_ohne_objekt_ist_ein_fehler_der_bibliothek(
        methode, route, art, koerper):
    """Die Parser dahinter lesen mit ``.get()`` -- eine Liste oder ein String
    entkam deshalb als ``AttributeError`` (Review 11.09.2026, per Attrappe
    belegt). Die Bibliothek verspricht, dass ``except EduSharingError`` alles
    faengt; der Proxy haelt es fuer respond und images ueber ``call()``.

    Rohe Koerper, weil ``httpx.Response(json=None)`` gar keinen schickt -- das
    waere der schon abgedeckte Fall "kein JSON", nicht JSON ``null``."""
    from edusharing.errors import EduSharingError
    aufrufe = []

    def handler(_request):
        return httpx.Response(200, content=koerper,
                              headers={"content-type": "application/json"})
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(EduSharingError, match=f"/{route} "):
            await getattr(vorlagen, methode)(["a"], context_node_id=KNOTEN, **art)
    assert len(aufrufe) == 1, "eine 200 ist beantwortet -- kein zweiter Versuch"


# --- Aufgabe 8: suggest -- schreibt Vorschlaege ins Repositorium ------------
#
# Die Spec: "store them as suggestions in edu-sharing". Dieselbe Form, die
# ``node.suggestions.list()`` liest -- also derselbe Typ zurueck, und der Weg
# zu ``flows.accept_suggestion`` ist schon gebaut.

#: Gemessen am 11.09.2026 auf Staging: so sieht ein Eintrag der Antwort aus --
#: angelegt unter dem eigenen Konto des Gateways, nicht unter ``user``.
VORSCHLAG = {
    "id": "6aa3f0fa545be0bf6fb70026", "nodeId": KNOTEN, "propertyId": LRT,
    "value": APPLICATION, "status": "PENDING", "type": "AI", "confidence": 1.0,
    "version": "1.0", "description": "Created by B-API",
    "created": "2026-09-11T12:16:04.676Z",
    "createdBy": {"authorityName": "admin@B-API", "authorityType": "USER",
                  "editable": False},
}


async def test_suggest_schickt_widgets_und_die_fuenf_felder():
    aufrufe = []
    async with _vorlagen(_antwortet([VORSCHLAG]), aufrufe) as vorlagen:
        await vorlagen.suggest(["suggestion_ai"], {LRT: "default"},
                               context_node_id=KNOTEN, variables={"cclom:title": "Luft"})
    koerper = _koerper(aufrufe[0])
    assert aufrufe[0].url.path == f"{PFAD}/suggestions"
    assert koerper["widgetAiConfigs"] == [{"widgetId": LRT, "aiConfigId": "default"}]
    assert koerper["variables"] == {"cclom:title": ["Luft"]}
    assert {"metadataSet", "configIds", "user", "contextNodeId"} <= set(koerper)


async def test_suggest_liefert_dieselben_vorschlaege_wie_das_repositorium():
    """Die gemessene Antwort, Feld fuer Feld in den Typ, den auch
    ``node.suggestions.list()`` liefert -- dort las der Live-Lauf dieselben
    IDs wieder."""
    async with _vorlagen(_antwortet([VORSCHLAG])) as vorlagen:
        [vorschlag] = await vorlagen.suggest(["suggestion_ai"], {LRT: "default"},
                                             context_node_id=KNOTEN)
    assert (vorschlag.id, vorschlag.property, vorschlag.value, vorschlag.status) == (
        "6aa3f0fa545be0bf6fb70026", LRT, APPLICATION, "PENDING")
    assert (vorschlag.author, vorschlag.why, vorschlag.confidence) == (
        "admin@B-API", "Created by B-API", 1.0)


async def test_suggest_ohne_widget_wird_abgewiesen():
    from edusharing.errors import ValidationError
    aufrufe = []
    async with _vorlagen(_antwortet([]), aufrufe) as vorlagen:
        with pytest.raises(ValidationError, match="widget"):
            await vorlagen.suggest(["suggestion_ai"], {}, context_node_id=KNOTEN)
    assert aufrufe == []


@pytest.mark.parametrize("status", [502, 504])
async def test_suggest_wiederholt_keine_antwort_die_nach_getaner_arbeit_kam(status):
    """Ein 502 oder 504 kann zurueckkommen, nachdem die Vorschlaege schon
    angelegt sind. Ein zweiter Versuch legte sie ein zweites Mal an."""
    from edusharing.errors import EduSharingError
    aufrufe = []
    handler = _antwortet({"message": "gateway"}, status)
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(EduSharingError, match="Check before sending it again"):
            await vorlagen.suggest(["a"], {LRT: "default"}, context_node_id=KNOTEN)
    assert len(aufrufe) == 1


async def test_suggest_wiederholt_eine_503():
    """Ueberlastet, bevor etwas geschah -- das darf nochmal."""
    aufrufe = []
    handler = _folge((503, {"message": "busy"}), (200, [VORSCHLAG]))
    async with _vorlagen(handler, aufrufe) as vorlagen:
        vorschlaege = await vorlagen.suggest(["a"], {LRT: "default"}, context_node_id=KNOTEN)
    assert len(vorschlaege) == 1
    assert len(aufrufe) == 2


async def test_suggest_wiederholt_keine_verbindungsstoerung():
    """Die Anfrage kann angekommen sein, bevor die Leitung riss."""
    from edusharing.errors import EduSharingError
    aufrufe = []

    def handler(_request):
        raise httpx.ReadTimeout("zu langsam")
    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(EduSharingError, match="may have arrived"):
            await vorlagen.suggest(["a"], {LRT: "default"}, context_node_id=KNOTEN)
    assert len(aufrufe) == 1


@pytest.mark.parametrize("fehler", [httpx.ConnectError("abgewiesen"),
                                    httpx.ConnectTimeout("keine Verbindung"),
                                    httpx.PoolTimeout("kein freier Platz")])
async def test_suggest_wiederholt_was_vor_dem_senden_scheiterte(fehler):
    """Eine Verbindung, die nie zustande kam, hat nichts gesendet -- also auch
    nichts gespeichert. "may have arrived" schickte den Aufrufer nach etwas
    suchen, das es nicht geben kann (Review 11.09.2026). Dieselbe Grenze zieht
    der Transport des Repositoriums mit ``_BEFORE_SENDING``."""
    aufrufe = []
    versuche = iter([fehler, None])

    def handler(_request):
        vorher = next(versuche)
        if vorher:
            raise vorher
        return httpx.Response(200, json=[VORSCHLAG])
    async with _vorlagen(handler, aufrufe) as vorlagen:
        vorschlaege = await vorlagen.suggest(["a"], {LRT: "default"},
                                             context_node_id=KNOTEN)
    assert len(aufrufe) == 2
    assert [v.id for v in vorschlaege] == [VORSCHLAG["id"]]


async def test_eine_antwort_ohne_liste_ist_ein_fehler_und_keine_leere_menge():
    """Eine leere Liste hiesse "nichts vorgeschlagen". Eine unerwartete Form
    sagt das nicht -- sie still als leer zu lesen, verschwiege, dass der Aufrufer
    nicht weiss, was angelegt wurde."""
    from edusharing.errors import EduSharingError
    async with _vorlagen(_antwortet({"unerwartet": True})) as vorlagen:
        with pytest.raises(EduSharingError, match="list"):
            await vorlagen.suggest(["a"], {LRT: "default"}, context_node_id=KNOTEN)


# --- Aufgabe 9: qas -- EXPERIMENTAL, schreibt ebenfalls ----------------------

#: Gemessen am 11.09.2026 auf Staging, samt dem kaputten ``created`` -- das
#: Jahr 58665. Genau deshalb gibt ``qas`` die Dicts unveraendert zurueck.
QA = {"answer": "Aus Stickstoff, Sauerstoff und Spurengasen.",
      "created": "+58665-03-31T18:28:35Z", "createdBy": "admin@B-API",
      "edited": False, "educationalLevel": None, "id": "6aa3f1e5545be0bf6fb70091",
      "lastReviewed": None, "nodeId": KNOTEN, "question": "Woraus besteht Luft?",
      "reviewedBy": None, "usedText": "# Luft\n\nLuft ist ein Gasgemisch ..."}


async def test_qas_schickt_nur_die_knoten():
    """Die Spec: ``EduSharingQaRequest`` hat genau ``nodeIds`` -- keine
    Konfiguration, kein Metadatenset. Die Fragen macht ein externer Dienst."""
    aufrufe = []
    async with _vorlagen(_antwortet([QA]), aufrufe) as vorlagen:
        paare = await vorlagen.qas([KNOTEN])
    assert aufrufe[0].url.path == f"{PFAD}/qas"
    assert _koerper(aufrufe[0]) == {"nodeIds": [KNOTEN]}
    assert paare == [QA]


@pytest.mark.parametrize("knoten", [[], "ein-einzelner-string", [""]])
async def test_qas_prueft_die_knoten_vor_dem_senden(knoten):
    from edusharing.errors import ValidationError
    aufrufe = []
    async with _vorlagen(_antwortet([]), aufrufe) as vorlagen:
        with pytest.raises(ValidationError):
            await vorlagen.qas(knoten)
    assert aufrufe == []


async def test_qas_wiederholt_keine_504():
    from edusharing.errors import EduSharingError
    aufrufe = []
    async with _vorlagen(_antwortet({"message": "gateway"}, 504), aufrufe) as vorlagen:
        with pytest.raises(EduSharingError):
            await vorlagen.qas([KNOTEN])
    assert len(aufrufe) == 1


# --- Aufgabe 10: Lebenszyklus und Umgebung ----------------------------------

@pytest.fixture
def umgebung(monkeypatch):
    monkeypatch.setenv("B_API_KEY", "aus-der-umgebung")
    monkeypatch.setenv("B_API_BASE_URL", GATEWAY)
    monkeypatch.setenv("EDU_SHARING_METADATASET", "mds_oeh")
    return monkeypatch


async def test_from_env_liest_schluessel_adresse_und_metadatenset(umgebung):
    """Dieselben Variablen wie ``BildungsAPI`` und ``Repository`` -- wer den
    Proxy schon eingerichtet hat, hat den Template-Modus mit eingerichtet."""
    async with BapiTemplates.from_env() as vorlagen:
        assert vorlagen.base_url == GATEWAY
        assert vorlagen.metadataset == "mds_oeh"


@pytest.mark.parametrize("variable", ["B_API_KEY", "B_API_BASE_URL", "EDU_SHARING_METADATASET"])
def test_from_env_nennt_die_fehlende_variable(umgebung, variable):
    from edusharing.errors import EduSharingError
    umgebung.delenv(variable)
    with pytest.raises(EduSharingError, match=variable):
        BapiTemplates.from_env()


async def test_from_env_nimmt_das_metadatenset_auch_als_argument(umgebung):
    umgebung.delenv("EDU_SHARING_METADATASET")
    async with BapiTemplates.from_env(metadataset="mds_x") as vorlagen:
        assert vorlagen.metadataset == "mds_x"


async def test_from_env_nimmt_die_adresse_auch_als_argument(umgebung):
    """Audit TST-23-1: der Zweig, in dem die Umgebung keine Adresse nennt und
    das Argument sie traegt, lief nie."""
    umgebung.delenv("B_API_BASE_URL")
    async with BapiTemplates.from_env(base_url="https://anderes.example.test") as vorlagen:
        assert vorlagen.base_url == "https://anderes.example.test"


async def test_ein_argument_schlaegt_seine_variable(umgebung):
    """Wer die Adresse ausdruecklich nennt, meint sie -- sonst ginge der
    Schluessel an einen Host, den er gerade nicht gewaehlt hat."""
    async with BapiTemplates.from_env(base_url="https://anderes.example.test",
                                      metadataset="mds_x") as vorlagen:
        assert vorlagen.base_url == "https://anderes.example.test"
        assert vorlagen.metadataset == "mds_x"


# --- Ablehnungen, die nie liefen (Audit TST-23-1, 23.09.2026) ----------------
#
# Der Proxy-Client deckte dieselben Wege ab, der Template-Client nicht.

async def test_ein_zu_langes_retry_after_wird_nicht_abgewartet():
    """Laenger als ``max_retry_after`` ist kein zweiter Versuch mehr, sondern
    ein Aufhaenger: der Fehler geht mit der Zahl an den Aufrufer."""
    from edusharing.errors import RateLimitedError
    aufrufe = []

    def handler(_request):
        return httpx.Response(429, headers={"Retry-After": "3600"},
                              json={"message": "slow down"})

    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(RateLimitedError) as fehler:
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert fehler.value.retry_after == 3600.0
    assert len(aufrufe) == 1


async def test_eine_umleitung_wird_gemeldet_statt_ihr_zu_folgen():
    """Wer umleitet, bekaeme sonst den ``X-API-KEY`` mitgeschickt."""
    from edusharing.errors import EduSharingError
    aufrufe = []

    def handler(_request):
        return httpx.Response(302, headers={"Location": "https://fremd.example.test/x"})

    async with _vorlagen(handler, aufrufe) as vorlagen:
        with pytest.raises(EduSharingError) as fehler:
            await vorlagen.chat(["a"], context_node_id=KNOTEN)
    assert fehler.value.status == 302
    assert "fremd.example.test" in str(fehler.value)
    assert len(aufrufe) == 1


@pytest.mark.parametrize(("feld", "wert"), [("api_key", ""), ("metadataset", "")])
def test_schluessel_und_metadatenset_sind_pflicht(feld, wert):
    from edusharing.errors import EduSharingError
    argumente = {"api_key": "k", "base_url": GATEWAY, "metadataset": "mds_oeh", feld: wert}
    with pytest.raises(EduSharingError):
        BapiTemplates(**argumente)


def test_zugangsdaten_in_der_adresse_werden_abgewiesen_und_nicht_wiederholt():
    """Der b-api-Schluessel gehoert in ``api_key``. Eine Adresse wird
    protokolliert -- steht ein Passwort darin, steht es in jedem Protokoll."""
    from edusharing.errors import EduSharingError
    with pytest.raises(EduSharingError) as fehler:
        BapiTemplates("k", base_url="https://nutzer:GEHEIM@gateway.example.test",
                      metadataset="mds_oeh")
    assert "GEHEIM" not in str(fehler.value)


async def test_ein_mitgebrachter_client_bleibt_offen():
    """Er gehoert dem, der ihn mitbrachte -- vielleicht teilt er ihn mit
    ``BildungsAPI``. Das ist genau der vorgesehene Weg zu einem gemeinsamen
    Verbindungspool."""
    eigener = httpx.AsyncClient(transport=httpx.MockTransport(_antwortet(COMPLETION)))
    async with BapiTemplates("k", base_url=GATEWAY, metadataset="m", client=eigener):
        pass
    assert not eigener.is_closed
    await eigener.aclose()


async def test_ein_eigener_client_wird_geschlossen():
    vorlagen = BapiTemplates("k", base_url=GATEWAY, metadataset="m")
    async with vorlagen:
        pass
    assert vorlagen._client.is_closed


def test_mitgebrachter_client_und_timeout_widersprechen_sich():
    """Dieselbe Regel wie ueberall in der Bibliothek: ein fremder Client hat
    seinen eigenen Timeout, ein zweiter waere wirkungslos."""
    from edusharing.errors import EduSharingError
    with pytest.raises(EduSharingError):
        BapiTemplates("k", base_url=GATEWAY, metadataset="m",
                      client=httpx.AsyncClient(), timeout=5)


def test_die_parallelitaet_ist_eine_ganze_zahl_ab_eins():
    from edusharing.errors import EduSharingError
    with pytest.raises(EduSharingError):
        BapiTemplates("k", base_url=GATEWAY, metadataset="m", max_concurrency=0)


def test_die_darstellung_zeigt_keinen_schluessel():
    vorlagen = BapiTemplates("geheimer-schluessel", base_url=GATEWAY, metadataset="m")
    assert "geheimer-schluessel" not in repr(vorlagen)


@pytest.mark.parametrize("modul", ["templates", "template_body"])
def test_der_template_modus_braucht_keinen_proxy(modul):
    """Die Vorgabe: unabhaengig voneinander nutzbar. Keine Instanz von
    ``BildungsAPI`` wird gebaut, keine gebraucht -- in keinem der beiden
    Module des Template-Modus."""
    import importlib
    assert "BildungsAPI" not in vars(importlib.import_module(f"edusharing.bapi.{modul}"))


@pytest.mark.parametrize("wert", [
    "gateway.example.test",                  # ohne Schema
    "ftp://gateway.example.test",
    "https://gateway.example.test/?x=1",
    "   ",
])
def test_eine_unbrauchbare_gateway_adresse_wird_abgelehnt(wert):
    """Dieselbe Pruefung wie bei ``BildungsAPI`` -- beide tragen den Schluessel
    an jeder Anfrage, und beide nahmen bis dahin jede Zeichenkette an
    (Audit SEC-20-1)."""
    from edusharing.errors import EduSharingError
    with pytest.raises(EduSharingError):
        BapiTemplates("k", base_url=wert, metadataset="mds_oeh")
