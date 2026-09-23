"""Der Page Builder: die Seite, die eine Sammlung rendert.

Alles hier ist am 28.08.2026 gegen Staging gemessen, an der Sammlung
``Deutsch`` und ihrem Konfigurationsordner
``f2020460-d304-46b4-8204-60d304d6b4c5``:

* Eine Sammlung mit Seite traegt ``ccm:page_config_ref`` -- einen Store-Ref auf
  einen Ordner vom Typ ``ccm:map``. Ohne die Eigenschaft gibt es keine Seite.
* Der Ordner traegt ``ccm:page_config``. Gemessen:
  ``{"variants":[<zwei Store-Refs>]}`` -- **ohne** ``default``. Ein Dokument
  ohne ``default`` rendert die erste Variante der Liste. "Keine festgelegt" und
  "die erste festgelegt" sehen gleich aus und sind verschiedene Zustaende.
* Die Varianten sind die Kinder des Ordners, je mit ``ccm:page_variant_config``
  (3,5 bis 4,1 kB JSON). Die Kinderliste sendet ``propertyFilter=-all-``, also
  kommen die Dokumente mit -- eine Seite kostet zwei Anfragen.
* ``ccm:page_variant_is_template`` ist ein **String** (``"false"``).
* Von 10 Grid-Elementen der gemessenen Variante trug **eines gar keine**
  ``nodeId``. Ein Element ohne Knoten ist der Normalfall, kein Fehler.
* Am Dokument validiert nichts: gemessen (MCP, 09.08.2026) nahm
  ``POST …/property?property=ccm:page_config`` die Zeichenkette
  ``"not json at all"`` mit 200 an und speicherte sie woertlich.
"""

import json

import httpx
import pytest

from edusharing import AsyncRepository
from edusharing.errors import ConflictError, SilentDropError
from edusharing.pages import CuratedPage, PageVariant, Swimlane, SwimlaneItem

REPO = "https://repo.test/edu-sharing"

SAMMLUNG = "col-1"
ORDNER = "folder-1"
V1 = "var-1"
V2 = "var-2"


def _ref(node_id: str) -> str:
    return f"workspace://SpacesStore/{node_id}"


def _variant_config(*, lanes: list[dict] | None = None,
                    variables: dict | None = None) -> str:
    doc: dict = {"structure": {"swimlanes": lanes if lanes is not None else [
        {"heading": "Themen", "type": "container", "grid": [
            {"cols": "6", "rows": "1", "item": "wlo-collection-chips",
             "nodeId": _ref("widget-1")},
        ]},
        {"heading": "Redaktion", "type": "container", "grid": [
            # Gemessen: ein Element ganz ohne nodeId.
            {"cols": "6", "rows": "1", "item": "wlo-editorial-members"},
        ]},
    ]}}
    if variables is not None:
        doc["variables"] = variables
    return json.dumps(doc)


def _node(node_id: str, *, typ: str = "ccm:map", titel: str = "",
          props: dict | None = None) -> dict:
    eigenschaften = {"cm:name": [titel or node_id], "cclom:title": [titel or node_id]}
    eigenschaften.update(props or {})
    return {"ref": {"id": node_id, "repo": "-home-"}, "type": typ,
            "title": titel or node_id, "name": titel or node_id,
            "properties": eigenschaften, "access": ["Read", "Write"]}


#: ``page_config=None`` heisst "die Eigenschaft fehlt ganz" -- ein eigener Fall
#: neben "steht da, ist aber kaputt". Ohne Sentinel liessen sich die beiden im
#: Test nicht auseinanderhalten.
VORGABE = object()


class Instanz:
    """Ein Repositorium, das sich merkt, was auf den Ordner geschrieben wurde."""

    def __init__(self, *, seiten_ref: str | None = _ref(ORDNER),
                 page_config: str | object | None = VORGABE,
                 varianten: list[dict] | None = None,
                 taub: bool = False) -> None:
        self.page_config = (
            json.dumps({"variants": [_ref(V1), _ref(V2)]})
            if page_config is VORGABE else page_config
        )
        self.seiten_ref = seiten_ref
        self.varianten = varianten if varianten is not None else [
            _node(V1, titel="Variante A", props={
                "ccm:page_variant_config": [_variant_config()],
                "ccm:page_variant_is_template": ["false"]}),
            _node(V2, titel="Variante B", props={
                "ccm:page_variant_config": [_variant_config()],
                "ccm:page_variant_is_template": ["false"]}),
        ]
        # taub=True bildet den gemessenen stillen Verlust nach: 200, nichts
        # gespeichert.
        self.taub = taub
        self.geschrieben: list[str] = []

    def _ordner(self) -> dict:
        props = {}
        if self.page_config is not None:
            props["ccm:page_config"] = [self.page_config]
        return _node(ORDNER, titel=f"PAGE_{ORDNER}", props=props)

    def handler(self, request: httpx.Request) -> httpx.Response:
        pfad = request.url.path
        if pfad.endswith("/property"):
            self.geschrieben.append(request.url.params["property"])
            koerper = json.loads(request.content)
            if not self.taub:
                self.page_config = koerper[0]
            return httpx.Response(200, content=b"")
        if pfad.endswith("/children"):
            return httpx.Response(200, json={
                "nodes": self.varianten,
                "pagination": {"total": len(self.varianten), "from": 0}})
        if pfad.endswith(f"/{ORDNER}/metadata"):
            return httpx.Response(200, json={"node": self._ordner()})
        for variante in self.varianten:
            if pfad.endswith(f"/{variante['ref']['id']}/metadata"):
                return httpx.Response(200, json={"node": variante})
        props = {}
        if self.seiten_ref is not None:
            props["ccm:page_config_ref"] = [self.seiten_ref]
        return httpx.Response(200, json={
            "node": _node(SAMMLUNG, titel="Deutsch", props=props)})

    def repo(self) -> AsyncRepository:
        return AsyncRepository(
            REPO, backoff_base=0.0,
            client=httpx.AsyncClient(transport=httpx.MockTransport(self.handler)))


# --- F09 (Fremdpruefung 09.09.2026): die Variante hinter dem Deckel --------
#
# ``_read`` las einmalig hoechstens 50 Kinder. Lag die konfigurierte
# Standardvariante dahinter, wurde ``rendered_id`` geleert und auf die erste
# geladene zurueckgefallen -- gemessen am 09.09.2026 mit 51 Varianten und
# ``default="v50"``: gemeldet wurde ``v0``, ``rendered_id=""`` und
# ``by_position=True``. Beide Auskuenfte waren falsch: eine Standardvariante
# ist festgelegt, sie war nur nicht geladen.
#
# Gemessen sind reale Seiten klein (93 von 99 tragen genau eine Variante).
# Darum wird nicht paginiert, sondern gesagt, dass nicht alles gelesen wurde.


class MitSeitengrenze(Instanz):
    """Eine Instanz, die ``maxItems`` fuer die Kinderliste beachtet."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/children"):
            wieviel = int(request.url.params.get("maxItems") or 20)
            gezeigt = self.varianten[:wieviel]
            return httpx.Response(200, json={
                "nodes": gezeigt,
                "pagination": {"total": len(self.varianten), "from": 0,
                               "count": len(gezeigt)}})
        return super().handler(request)


def _viele_varianten(wieviele: int) -> list[dict]:
    return [_node(f"v{i}", titel=f"Variante {i}", props={
        "ccm:page_variant_config": [_variant_config()],
        "ccm:page_variant_is_template": ["false"]}) for i in range(wieviele)]


async def test_eine_gekuerzte_variantenliste_sagt_es():
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(51)],
                                "default": _ref("v50")}),
        varianten=_viele_varianten(51))
    seite = await _seite(instanz)
    assert seite is not None
    assert seite.truncated is True
    assert len(seite.variants) == 50


async def test_eine_gekuerzte_liste_erfindet_keine_ersatzvariante():
    """Der eigentliche Fehler: ``v0`` wurde als gerenderte Variante gemeldet.

    Der Seitenbauer rendert ``v50``. Ohne sie gelesen zu haben, ist jede
    Antwort auf "was sieht ein Besucher" geraten -- also wird keine gegeben.
    """
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(51)],
                                "default": _ref("v50")}),
        varianten=_viele_varianten(51))
    seite = await _seite(instanz)
    assert seite is not None
    assert seite.rendered is None
    assert seite.by_position is False, (
        "'keine festgelegt' ist etwas anderes als 'nicht gelesen'")


async def test_eine_vollstaendige_liste_meldet_weiterhin_ihre_variante():
    """Die Gegenprobe. Ohne sie waere die Wache gruen, wenn jede Seite
    ``truncated`` meldet und nie eine gerenderte Variante nennt."""
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(3)],
                                "default": _ref("v1")}),
        varianten=_viele_varianten(3))
    seite = await _seite(instanz)
    assert seite is not None
    assert seite.truncated is False
    assert seite.rendered_id == "v1"
    assert seite.rendered is not None and seite.rendered.id == "v1"
    assert seite.by_position is False


async def test_ohne_festgelegte_variante_rendert_weiterhin_die_erste():
    """Die zweite Gegenprobe: ``by_position`` bleibt fuer den Fall, fuer den
    es gemacht ist -- ein Dokument ohne ``default``."""
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(3)]}),
        varianten=_viele_varianten(3))
    seite = await _seite(instanz)
    assert seite is not None
    assert seite.truncated is False
    assert seite.by_position is True
    assert seite.rendered is not None and seite.rendered.id == "v0"


async def test_eine_nicht_geladene_variante_wird_nicht_als_unbekannt_abgewiesen():
    """``choose()`` sagte "is not a variant of this page" -- ueber eine
    Variante, die es gibt und die nur nicht gelesen wurde."""
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(51)],
                                "default": _ref("v50")}),
        varianten=_viele_varianten(51))
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        with pytest.raises(ValueError) as fehler:
            await knoten.page.render("v50")
    meldung = str(fehler.value)
    assert "50" in meldung and "51" in meldung, meldung
    assert "is not a variant" not in meldung


async def test_eine_geladene_variante_laesst_sich_auch_bei_kuerzung_waehlen():
    """Die Gegenprobe: der Deckel macht nicht die ganze Seite unbedienbar."""
    instanz = MitSeitengrenze(
        page_config=json.dumps({"variants": [_ref(f"v{i}") for i in range(51)],
                                "default": _ref("v50")}),
        varianten=_viele_varianten(51))
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        seite = await knoten.page.render("v3")
    assert seite.rendered_id == "v3"


async def _seite(instanz: Instanz) -> CuratedPage | None:
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        return await knoten.page.get()


# --- Das Variantendokument ------------------------------------------------

async def test_schwimmlinien_werden_gelesen():
    seite = await _seite(Instanz())
    linien = seite.variants[0].swimlanes
    assert [ln.heading for ln in linien] == ["Themen", "Redaktion"]
    assert linien[0].type == "container"


async def test_store_ref_wird_abgeschnitten():
    seite = await _seite(Instanz())
    assert seite.variants[0].swimlanes[0].items[0].node_id == "widget-1"


async def test_element_ohne_knoten_bleibt_erhalten():
    """Gemessen: 1 von 10 Grid-Elementen traegt keine nodeId. Wer sie
    wegfiltert, verliert eine Zeile der Seite."""
    seite = await _seite(Instanz())
    element = seite.variants[0].swimlanes[1].items[0]
    assert element.widget == "wlo-editorial-members"
    assert element.node_id is None


async def test_vorlagen_flag_kommt_als_zeichenkette():
    instanz = Instanz(varianten=[
        _node(V1, titel="Vorlage", props={
            "ccm:page_variant_config": [_variant_config()],
            "ccm:page_variant_is_template": ["true"]}),
        _node(V2, titel="Echt", props={
            "ccm:page_variant_config": [_variant_config()],
            "ccm:page_variant_is_template": ["false"]}),
    ])
    seite = await _seite(instanz)
    assert [v.is_template for v in seite.variants] == [True, False]


async def test_kaputtes_dokument_wirft_nicht():
    """Ein Lesepfad darf an einem Dokument, das niemand validiert, nicht
    scheitern -- er sagt, dass er es nicht lesen konnte."""
    instanz = Instanz(varianten=[
        _node(V1, props={"ccm:page_variant_config": ["not json at all"]}),
    ])
    seite = await _seite(instanz)
    assert seite.variants[0].readable is False
    assert seite.variants[0].swimlanes == ()


async def test_variante_ohne_dokument_ist_lesbar_aber_leer():
    """Kein Dokument ist etwas anderes als ein kaputtes."""
    instanz = Instanz(varianten=[_node(V1)])
    seite = await _seite(instanz)
    assert seite.variants[0].readable is True
    assert seite.variants[0].swimlanes == ()


async def test_seite_ohne_schwimmlinien_ist_lesbar():
    """Gemessen am 28.08.2026: die Sammlung Hexen traegt eine Seite mit einer
    Variante, deren Dokument lesbar ist und deren swimlanes leer sind. "Hat
    eine Seite" und "hat Inhalt" sind zwei Fragen."""
    instanz = Instanz(varianten=[_node(V1, props={
        "ccm:page_variant_config": [_variant_config(lanes=[])]})])
    seite = await _seite(instanz)
    assert seite.variants[0].readable is True
    assert seite.variants[0].swimlanes == ()
    assert seite.rendered is not None, "die Variante gibt es, sie zeigt nur nichts"


async def test_voreinstellung_wird_gelesen():
    """Gemessen: der variables-Block traegt die Voreinstellung des
    Profil-Waehlers, und die Bildungsstufen stehen dort als EINE
    komma-getrennte Zeichenkette, nicht als Liste."""
    instanz = Instanz(varianten=[_node(V1, props={
        "ccm:page_variant_config": [_variant_config(variables={
            "virtual:profiling_widget_intention": "teach",
            "virtual:profiling_widget_education_level": "uri/sek_1, uri/sek_2",
        })]})])
    seite = await _seite(instanz)
    assert seite.variants[0].intention == "teach"
    assert seite.variants[0].education_levels == ("uri/sek_1", "uri/sek_2")


async def test_zielgruppenfelder_werden_nicht_aus_der_voreinstellung_geraten():
    """Die offiziellen Felder und die Voreinstellung sind verschiedene
    Aussagen -- das MCP hat am 11.08.2026 gemessen, dass sie sich
    widersprechen. Keine wird auf die andere zurueckgefuehrt."""
    instanz = Instanz(varianten=[_node(V1, props={
        "ccm:page_variant_config": [_variant_config(variables={
            "virtual:profiling_widget_intention": "teach"})]})])
    seite = await _seite(instanz)
    assert seite.variants[0].intention == "teach"
    assert seite.variants[0].target_group is None


async def test_knoten_ids_sind_flach_und_entdoppelt():
    instanz = Instanz(varianten=[_node(V1, props={
        "ccm:page_variant_config": [_variant_config(lanes=[
            {"heading": "a", "grid": [{"item": "x", "nodeId": _ref("w1")},
                                      {"item": "y", "nodeId": _ref("w1")}]},
            {"heading": "b", "grid": [{"item": "z", "nodeId": _ref("w2")},
                                      {"item": "leer"}]},
        ])]})])
    seite = await _seite(instanz)
    assert seite.variants[0].node_ids == ("w1", "w2")


# --- Die Seite ------------------------------------------------------------

async def test_sammlung_ohne_seite_ergibt_none():
    assert await _seite(Instanz(seiten_ref=None)) is None


async def test_ohne_default_rendert_die_erste_variante():
    """Gemessen: das Dokument der Sammlung Deutsch hat keinen default."""
    seite = await _seite(Instanz())
    assert seite.by_position is True
    assert seite.rendered.id == V1
    assert seite.rendered_id == ""


async def test_default_steht_vorn():
    instanz = Instanz(page_config=json.dumps(
        {"variants": [_ref(V1), _ref(V2)], "default": _ref(V2)}))
    seite = await _seite(instanz)
    assert seite.by_position is False
    assert seite.rendered.id == V2
    assert [v.id for v in seite.variants] == [V2, V1]


async def test_default_auf_eine_verschwundene_variante():
    """Das Dokument nennt einen default, den Knoten gibt es nicht mehr. Der
    Page Builder rendert dann die erste der Liste -- genau wie ohne default.
    Beides gleich zu melden ist richtig; der aufgezeichnete Wert steht fuer
    eine Fehlersuche weiter in ``document``."""
    instanz = Instanz(page_config=json.dumps(
        {"variants": [_ref(V1), _ref(V2)], "default": _ref("weg-1")}))
    seite = await _seite(instanz)
    assert seite.by_position is True
    assert seite.rendered.id == V1
    assert "weg-1" in seite.document


async def test_variante_ausserhalb_des_dokuments_geht_nicht_verloren():
    """Der Ordner kann Kinder haben, die das Dokument nie genannt hat. Sie
    hinten anzuhaengen ist ehrlicher, als sie zu verschweigen."""
    instanz = Instanz(page_config=json.dumps({"variants": [_ref(V2)]}))
    seite = await _seite(instanz)
    assert [v.id for v in seite.variants] == [V2, V1]


async def test_ordner_ohne_kinder_rendert_nichts():
    instanz = Instanz(varianten=[])
    seite = await _seite(instanz)
    assert seite.variants == ()
    assert seite.rendered is None


async def test_variante_nachschlagen():
    seite = await _seite(Instanz())
    assert seite.variant(V2).title == "Variante B"
    assert seite.variant("gibtesnicht") is None


async def test_ordner_id_wird_gemeldet():
    seite = await _seite(Instanz())
    assert seite.folder_id == ORDNER
    assert seite.collection_id == SAMMLUNG


# --- Schreiben ------------------------------------------------------------

async def test_umstellen_setzt_den_default_als_store_ref():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        seite = await knoten.page.render(V2)
    assert instanz.geschrieben == ["ccm:page_config"]
    assert json.loads(instanz.page_config)["default"] == _ref(V2)
    assert seite.rendered.id == V2
    assert seite.by_position is False


async def test_unbekannte_schluessel_bleiben_erhalten():
    """Die uebrigen Schluessel gehoeren dem Page Builder. Ein Dokument neu zu
    komponieren wuerfe weg, was diese Bibliothek nie gesehen hat."""
    instanz = Instanz(page_config=json.dumps(
        {"variants": [_ref(V1), _ref(V2)], "layout": {"tiefe": 3}}))
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        await knoten.page.render(V2)
    gespeichert = json.loads(instanz.page_config)
    assert gespeichert["layout"] == {"tiefe": 3}
    assert gespeichert["variants"] == [_ref(V1), _ref(V2)]


async def test_stiller_verlust_wird_gemeldet():
    instanz = Instanz(taub=True)
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        with pytest.raises(SilentDropError):
            await knoten.page.render(V2)


@pytest.mark.parametrize("dokument, grund", [
    (None, "kein Dokument"),
    ("not json at all", "kein JSON"),
    ("[1, 2]", "kein Objekt"),
    ('{"default": "x"}', "keine variants-Liste"),
])
async def test_verweigert_kaputte_dokumente(dokument, grund):
    """Gemessen: die Instanz nimmt jeden Unsinn mit 200 an. Ein kaputtes
    Dokument faellt nicht hier auf, sondern spaeter im Page Builder, auf einer
    oeffentlichen Seite -- also wird hier verweigert statt repariert."""
    instanz = Instanz(page_config=dokument)
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        with pytest.raises(ConflictError):
            await knoten.page.render(V2)
    assert instanz.geschrieben == [], f"trotz {grund} geschrieben"


async def test_verweigert_fremde_variante():
    """Ein default ausserhalb von variants[] rendert nichts -- und die Instanz
    pruefte es nicht."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        with pytest.raises(ValueError, match="var-fremd"):
            await knoten.page.render("var-fremd")
    assert instanz.geschrieben == []


async def test_umstellen_liest_selbst_und_nicht_aus_der_hand():
    """Zwischen Lesen und Schreiben liegt ein Fenster, das die Property-Route
    mangels ETag nicht schliessen kann. Klein zu halten ist alles, was geht --
    darum liest ``render`` selbst und nimmt kein Dokument entgegen, das ein
    Aufrufer vor einer Stunde geholt hat."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        veraltet = await knoten.page.get()
        assert not hasattr(veraltet, "render"), (
            "eine gehaltene Seite darf nicht schreiben koennen")
        instanz.page_config = json.dumps(
            {"variants": [_ref(V1), _ref(V2)], "spaeter": "dazugekommen"})
        await knoten.page.render(V2)
    assert json.loads(instanz.page_config)["spaeter"] == "dazugekommen"


async def test_variante_ist_kind_aber_nicht_im_dokument():
    """Ein Kind des Ordners, das das Dokument nie genannt hat, ist eine gueltige
    Variante zum Lesen -- aber als default wuerde es nichts rendern."""
    instanz = Instanz(page_config=json.dumps({"variants": [_ref(V1)]}))
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        seite = await knoten.page.get()
        assert seite.variant(V2) is not None
        with pytest.raises(ConflictError, match="variants"):
            await knoten.page.render(V2)
    assert instanz.geschrieben == []


async def test_umstellen_in_einem_aufruf():
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        seite = await knoten.page.render(V2)
    assert seite.rendered.id == V2


async def test_umstellen_ohne_seite_wird_erklaert():
    instanz = Instanz(seiten_ref=None)
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        with pytest.raises(ConflictError, match="ccm:page_config_ref"):
            await knoten.page.render(V2)
    assert instanz.geschrieben == []


# --- Wertobjekte ----------------------------------------------------------

def test_wertobjekte_sind_unveraenderlich():
    element = SwimlaneItem(widget="x", node_id=None)
    with pytest.raises(AttributeError):
        element.widget = "y"


async def test_repr_nennt_das_wesentliche_auch_an_der_seite():
    """Ein repr ist Werkzeug: wer eine Seite im Debugger ansieht, will
    Varianten und gerenderte Variante sehen, nicht eine Objektadresse."""
    instanz = Instanz()
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        seite = await knoten.page.get()
        assert "by position" in repr(seite)
        assert SAMMLUNG in repr(knoten.page)
    element = seite.variants[0].swimlanes[0].items[0]
    assert "widget-1" in repr(element)
    assert "2 items" not in repr(seite.variants[0].swimlanes[1])
    assert "1 items" in repr(seite.variants[0].swimlanes[1])


def test_repr_nennt_das_wesentliche():
    variante = PageVariant(
        id="v", title="T", is_template=False, target_group=None,
        educational_contexts=(), intention=None, education_levels=(),
        swimlanes=(Swimlane(heading="h", type="container", items=()),),
        readable=True)
    assert "v" in repr(variante) and "1" in repr(variante)


# --- COR-1: die Seitenkonfiguration sagt idempotent=True (Review 06.09.2026, F6)

async def test_die_seitenkonfiguration_wird_nach_abbruch_erneut_gesendet():
    instanz = Instanz()
    abgebrochen = []
    echt = instanz.handler

    def handler(request):
        if (request.method == "POST" and request.url.path.endswith("/property")
                and not abgebrochen):
            abgebrochen.append(1)
            raise httpx.ReadTimeout("abgebrochen", request=request)
        return echt(request)

    instanz.handler = handler
    async with instanz.repo() as repo:
        knoten = await repo.node(SAMMLUNG)
        await knoten.page.render(V2)
    assert abgebrochen == [1]
    assert instanz.geschrieben == ["ccm:page_config"]
