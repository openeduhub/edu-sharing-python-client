"""Was die generierte Schicht aus der Spezifikation macht.

Der Abgleich, den es schon gibt, prueft Methoden, Pfade und Syntax: hat jede
Operation der Spec eine Entsprechung, parst jede Datei. Was er **nicht**
prueft, ist, ob die deklarierten Antworten auch ankommen.

Befund F15 der Fremdpruefung vom 09.09.2026: fuer zwei Endpunkte kam die
dokumentierte HTTP-200-Antwort nicht an. ``GET .../permissions/jwt``
deklariert sie als ``application/text`` -- kein gueltiger MIME-Typ -- und
``GET /ltiplatform/v13/content`` als ``*/*``. Der Generator uebernimmt
beides nicht, die eingecheckten Parser hatten also keinen 200-Zweig, und mit
``raise_on_unexpected_status=True`` entstand ``UnexpectedStatus`` fuer
Status **200**.

Dazu die Doku: ``ARCHITECTURE`` nannte "die einzige verbleibende Warnung:
eine 500-Antwort". An der Spec ausgezaehlt sind es **sieben** Antworten,
davon zwei Erfolge. Ein Satz, der eine Pruefung beruhigt, statt sie zu
leiten -- also zaehlt ihn hier eine Wache nach.
"""

import ast
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from edusharing._generated.client import Client
from edusharing._generated.errors import UnexpectedStatus

WURZEL = Path(__file__).resolve().parent.parent
SPEC = WURZEL / "openapi" / "edu-sharing-11.0.json"

#: Inhaltstypen, aus denen der Generator einen Antwortzweig baut. Alles
#: andere laesst er fallen -- ohne Fehler, nur mit einer Warnung im Lauf.
VERSTANDEN = frozenset({
    "application/json", "application/octet-stream", "multipart/form-data",
    "application/x-www-form-urlencoded", "text/plain", "text/html",
})
METHODEN = frozenset({"get", "put", "post", "delete", "patch", "head", "options"})


def _erzeugungsweg() -> ModuleType:
    """``scripts/generate_client.py``, ohne es auszufuehren.

    Die Wache haengt an derselben Abbildung, die der Erzeugungsweg benutzt --
    eine zweite Liste hier waere eine, die auseinanderlaeuft.
    """
    pfad = WURZEL / "scripts" / "generate_client.py"
    spec = spec_from_file_location("generate_client", pfad)
    assert spec is not None and spec.loader is not None
    modul = module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _nicht_uebernommene_antworten() -> list[tuple[str, str, str, str]]:
    """``(Methode, Pfad, Status, Inhaltstyp)`` fuer jede Antwort, aus der der
    Generator nichts machen kann -- **nach** der Normalisierung, die der
    Erzeugungsweg auf die Spec anwendet."""
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    _erzeugungsweg().normalise_content_types(spec)
    gefunden = []
    for pfad, eintrag in spec.get("paths", {}).items():
        for methode, op in eintrag.items():
            if methode not in METHODEN:
                continue
            for status, antwort in (op.get("responses") or {}).items():
                for typ in (antwort.get("content") or {}):
                    if typ not in VERSTANDEN:
                        gefunden.append((methode.upper(), pfad, status, typ))
    return gefunden


def test_keine_erfolgsantwort_faellt_bei_der_erzeugung_weg():
    """Eine 2xx, die der Generator nicht uebernimmt, ist eine Operation, die
    es zwar gibt, deren Ergebnis aber niemand bekommt."""
    verloren = [e for e in _nicht_uebernommene_antworten() if e[2].startswith("2")]
    assert verloren == [], (
        "diese Erfolgsantworten kommen nicht in der generierten Schicht an: "
        f"{verloren}. UNUSABLE_TYPES in scripts/generate_client.py "
        "ergaenzen und neu erzeugen -- nicht die erzeugte Datei aendern.")


def test_die_abbildung_des_erzeugungswegs_trifft_die_spec():
    """Ein Eintrag in ``UNUSABLE_TYPES``, den die Spec nicht kennt, ist
    tote Konfiguration -- und die naechste Spec-Fassung merkt es nicht."""
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    roh = SPEC.read_text(encoding="utf-8")
    unbenutzt = [a for a in _erzeugungsweg().UNUSABLE_TYPES
                 if f'"{a}"' not in roh]
    assert unbenutzt == [], unbenutzt
    assert spec["paths"], "die Spec ist leer gelesen worden"


def test_die_zaehlwache_sieht_ueberhaupt_etwas():
    """Eine Wache, deren Ausdruck nichts trifft, ist still gruen. Gemessen am
    09.09.2026 vor der Normalisierung: sieben Antworten, sechsmal
    ``application/text`` am JWT-Endpunkt und einmal ``*/*`` an der
    LTI-Inhaltsroute."""
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    antworten = sum(
        len(a.get("content") or {})
        for eintrag in spec["paths"].values()
        for methode, op in eintrag.items() if methode in METHODEN
        for a in (op.get("responses") or {}).values())
    assert antworten > 1000, antworten


def _antwort(text: str) -> httpx.Response:
    return httpx.Response(200, text=text,
                          request=httpx.Request("GET", "https://x.test/"))


@pytest.mark.parametrize("modul,inhalt", [
    ("edusharing._generated.api.node_v_1.get_jwt", "ey.dummy.jwt"),
    ("edusharing._generated.api.lti_platform_v_13.get_content", "<html>ok</html>"),
])
def test_die_dokumentierte_zweihundert_kommt_an(modul, inhalt):
    """In beiden Betriebsarten: lose gibt es ein Ergebnis statt ``None``,
    streng keine Ausnahme ueber einen Status, den die Spec als Erfolg fuehrt."""
    from importlib import import_module

    endpunkt = import_module(modul)
    lose = Client(base_url="https://x.test", raise_on_unexpected_status=False)
    assert endpunkt._parse_response(client=lose, response=_antwort(inhalt)) == inhalt

    streng = Client(base_url="https://x.test", raise_on_unexpected_status=True)
    assert endpunkt._parse_response(client=streng, response=_antwort(inhalt)) == inhalt


def test_ein_unerwarteter_status_bleibt_unerwartet():
    """Die Gegenprobe: die strenge Betriebsart wirft weiterhin, wo die Spec
    nichts deklariert. Ohne sie waere die Wache gruen, wenn ``_parse_response``
    ueberhaupt nichts mehr prueft."""
    from edusharing._generated.api.node_v_1 import get_jwt

    streng = Client(base_url="https://x.test", raise_on_unexpected_status=True)
    antwort = httpx.Response(418, text="nope",
                             request=httpx.Request("GET", "https://x.test/"))
    with pytest.raises(UnexpectedStatus):
        get_jwt._parse_response(client=streng, response=antwort)


def test_die_fehlerzweige_lesen_weiterhin_json():
    """Die Gegenprobe zur Normalisierung -- und ein Fehler, den der erste
    Anlauf gemacht hat.

    Der JWT-Endpunkt deklariert **alle** seine Antworten als
    ``application/text``, die Fehler aber mit ``$ref: ErrorResponse``. Blind
    auf ``text/plain`` abzubilden gab ihnen ``from_dict(response.text)``:
    gemessen ``ValueError: dictionary update sequence element #0 has length
    1``, wo vorher ``None`` kam. Also entscheidet das **Schema**, nicht der
    erfundene Inhaltstyp.
    """
    from edusharing._generated.api.node_v_1 import get_jwt

    antwort = httpx.Response(
        404, json={"error": "DAOMissingException", "message": "weg"},
        request=httpx.Request("GET", "https://x.test/"))
    lose = Client(base_url="https://x.test", raise_on_unexpected_status=False)
    gelesen = get_jwt._parse_response(client=lose, response=antwort)
    assert gelesen is not None
    assert getattr(gelesen, "message", None) == "weg"


# --- R10 (Zweitpruefung 09.09.2026): Punktsegmente im generierten Client ---
#
# The former tests pinned the known gap. The 14 September implementation
# changes that contract: the reproducible generation pass must reject those
# values before HTTPX can normalize a destructive request's path.


@pytest.mark.parametrize("value", ["", ".", ".."])
@pytest.mark.parametrize("parameter", ["repository", "node"])
def test_generated_path_parameters_are_rejected_before_request_construction(value, parameter):
    from edusharing._generated.api.node_v_1 import delete

    arguments = {"repository": "-home-", "node": "normal-id", parameter: value}
    with pytest.raises(ValueError, match="Path parameters"):
        delete._get_kwargs(**arguments)


@pytest.mark.parametrize("node,encoded", [
    ("id.with.dots", "id.with.dots"), ("...", "..."),
    ("a/b?c#d", "a%2Fb%3Fc%23d"), ("%2E%2E", "%252E%252E"),
])
def test_generated_paths_keep_valid_identifiers_and_existing_escaping(node, encoded):
    from edusharing._generated.api.node_v_1 import delete

    kwargs = delete._get_kwargs(repository="-home-", node=node)
    assert kwargs["url"] == f"/node/v1/nodes/-home-/{encoded}"


def test_path_guard_generation_is_idempotent_and_preserves_other_code(tmp_path):
    endpoint = tmp_path / "api" / "nodes" / "get.py"
    endpoint.parent.mkdir(parents=True)
    source = ('from urllib.parse import quote\n\n'
              'def _get_kwargs(node: str):\n'
              '    return {"url": "/nodes/" + quote(str(node), safe="")}\n')
    endpoint.write_text(source, encoding="utf-8")
    generate = _erzeugungsweg()
    assert generate.guard_path_parameters(tmp_path) == 1
    guarded = endpoint.read_bytes()
    assert generate.guard_path_parameters(tmp_path) == 0
    assert endpoint.read_bytes() == guarded
    scope = {}
    exec(compile(guarded, str(endpoint), "exec"), scope)
    with pytest.raises(ValueError):
        scope["_get_kwargs"]("..")
    assert scope["_get_kwargs"]("a/b") == {"url": "/nodes/a%2Fb"}


def test_unexpected_generator_quote_shape_is_rejected(tmp_path):
    endpoint = tmp_path / "api" / "get.py"
    endpoint.parent.mkdir()
    endpoint.write_text('from urllib.parse import quote\n'
                        'def _get_kwargs(node: str):\n'
                        '    return quote(node, safe="")\n', encoding="utf-8")
    with pytest.raises(ValueError, match="quote expression"):
        _erzeugungsweg().guard_path_parameters(tmp_path)


@pytest.mark.parametrize("punkt", [".", ".."])
def test_die_komfortschicht_weist_dieselben_werte_ab(punkt):
    """Die andere Haelfte der Aussage. Ohne sie stuende hier nur ein Mangel;
    mit ihr steht da, wo die Grenze verlaeuft."""
    from edusharing.errors import EduSharingError
    from edusharing.urls import path_segment

    with pytest.raises(EduSharingError):
        path_segment(punkt)


#: Der Satz, den beide Sprachfassungen bei ``path_segment`` tragen muessen.
#: Nicht irgendein Vorkommen der Woerter -- die Aussage selbst.
GRENZE_GESAGT = {
    "docs/REFERENCE.md":
        "The generated layer rejects these values with ValueError before building a path.",
    "docs/REFERENCE.de.md":
        "Die generierte Schicht lehnt diese Werte vor dem Pfadaufbau mit ValueError ab.",
}


@pytest.mark.parametrize("rel", sorted(GRENZE_GESAGT))
def test_die_grenze_steht_in_der_dokumentation(rel):
    """Eine gemessene Grenze, die niemand aufschreibt, ist ein Fehler mit
    Aufschub.

    Der erste Anlauf dieses Tests pruefte, ob die Woerter "generated layer"
    und "path_segment" irgendwo in der Datei stehen -- das taten sie schon
    vorher, an anderer Stelle. Eine Wache, die den Satz nicht kennt, den sie
    schuetzt, ist gruen aus dem falschen Grund.
    """
    text = (WURZEL / rel).read_text(encoding="utf-8")
    assert GRENZE_GESAGT[rel] in text, rel


def test_kein_handgeschriebenes_modul_haengt_an_der_generierten_schicht():
    """Warum es keine kleine Stelle fuer diese Pruefung gibt -- und zugleich
    die Zusage, dass die generierte Schicht optional bleibt.

    Faellt dieser Test, gibt es plötzlich eine Grenze: dann gehoert die
    Pruefung dorthin.
    """
    quelle = WURZEL / "src" / "edusharing"
    haengt = []
    for pfad in sorted(quelle.rglob("*.py")):
        if "_generated" in pfad.parts:
            continue
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            namen: list[str] = []
            if isinstance(knoten, ast.Import):
                namen = [a.name for a in knoten.names]
            elif isinstance(knoten, ast.ImportFrom):
                namen = [knoten.module or ""]
                namen += ["." * knoten.level + (knoten.module or "")]
            if any("_generated" in n for n in namen):
                haengt.append(pfad.relative_to(quelle).as_posix())
                break
    assert haengt == [], haengt
