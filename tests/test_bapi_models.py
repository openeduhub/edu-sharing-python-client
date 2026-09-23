"""Welches Modell -- Wahl, Auslastung, Abkuendigung. Ohne Netz.

Alle Erwartungen stammen aus Messungen gegen die b-api (Staging). Die
Rumpfform steht in ``test_bapi_body.py``: zwei Fragen, die sich unabhaengig
voneinander bewegen.
"""

from datetime import date

import pytest

from edusharing.bapi.models import Model, pick_model
from edusharing.errors import ValidationError


def _m(mid, demand=0, status="ready", output=("text",)):
    return Model(id=mid, demand=demand, status=status,
                 input=("text",), output=tuple(output), owned_by="chat-ai", name=mid)


# --- Modellwahl ------------------------------------------------------------

def test_geringste_auslastung_gewinnt():
    """demand sagt die Wartezeit gut vorher: gemessen unter 0,6 s bei 0 und
    30 bis 41 s bei 5."""
    gewaehlt = pick_model([_m("a", demand=3), _m("b", demand=0), _m("c", demand=1)])
    assert gewaehlt.id == "b"


def test_nicht_bereite_modelle_werden_uebersprungen():
    gewaehlt = pick_model([_m("a", demand=0, status="loading"), _m("b", demand=4)])
    assert gewaehlt.id == "b"


def test_modelle_ohne_textausgabe_werden_uebersprungen():
    """Ein Embedding-Modell an /chat/completions antwortet mit
    '404 This is not a chat model'."""
    gewaehlt = pick_model([_m("embed", output=("embedding",)), _m("chat")])
    assert gewaehlt.id == "chat"


def test_bevorzugtes_modell_gewinnt_wenn_verfuegbar():
    gewaehlt = pick_model([_m("a", demand=0), _m("wunsch", demand=5)], prefer="wunsch")
    assert gewaehlt.id == "wunsch"


def test_bevorzugtes_modell_das_es_nicht_gibt_faellt_auf():
    """Modell-IDs aendern sich ohne Ankuendigung -- gemessen wurde aus
    deepseek-v4-flash binnen neun Tagen deepseek-v4-flash-0731, der alte Name
    antwortet seither mit 503. Ein stiller Wechsel auf ein anderes Modell
    waere schlimmer als ein Fehler."""
    with pytest.raises(ValidationError, match="wunsch"):
        pick_model([_m("a")], prefer="wunsch")


def test_ohne_brauchbares_modell_wird_das_gesagt():
    with pytest.raises(ValidationError):
        pick_model([_m("a", status="loading")])


def test_leere_liste():
    with pytest.raises(ValidationError):
        pick_model([])


# --- Abkuendigung ----------------------------------------------------------
#
# Gemessen am 31.08.2026: 57 von 132 OpenAI-Modellen tragen ein
# ``shutdown_date``, und acht verschiedene Termine kommen vor -- der frueheste
# (2026-07-23) lag zu dem Zeitpunkt bereits in der Vergangenheit, das Modell
# stand aber weiter in der Liste. Die AcademicCloud kennt das Feld nicht.

def test_shutdown_date_wird_gelesen():
    m = Model.from_response({"id": "gpt-4", "shutdown_date": "2026-10-23"})
    assert m.shutdown_date == "2026-10-23"


def test_ohne_shutdown_date_bleibt_es_leer():
    """Die AcademicCloud liefert das Feld nicht -- das ist keine Abkuendigung."""
    assert Model.from_response({"id": "glm-4.7"}).shutdown_date is None


@pytest.mark.parametrize("tag, erwartet", [
    (date(2026, 10, 22), False),   # davor
    (date(2026, 10, 23), True),    # am Tag selbst
    (date(2026, 10, 24), True),    # danach
])
def test_abgekuendigt_ab_dem_termin(tag, erwartet):
    m = Model.from_response({"id": "gpt-4", "shutdown_date": "2026-10-23"})
    assert m.is_retired_on(tag) is erwartet


def test_ohne_termin_nie_abgekuendigt():
    assert Model.from_response({"id": "x"}).is_retired_on(date(2099, 1, 1)) is False


def test_unlesbarer_termin_gilt_nicht_als_abgekuendigt():
    """Fremde Daten duerfen keine Ausnahme ausloesen.

    Ein unerwartetes Format ist ein Grund, nichts zu behaupten -- nicht ein
    Grund, das Modell fuer tot zu erklaeren.
    """
    m = Model.from_response({"id": "x", "shutdown_date": "demnaechst"})
    assert m.is_retired_on(date(2099, 1, 1)) is False


# --- Felder in der falschen Form (Audit COR-23-5) ---------------------------

def test_ein_termin_als_zahl_gilt_ebenso_nicht_als_abgekuendigt():
    """Audit COR-23-5 (23.09.2026): der Docstring sagt, eine unerwartete Form
    sei "ein Grund, nichts zu behaupten" -- gefangen wurde nur ``ValueError``,
    und eine Zahl warf ``TypeError``. Gemessen in ``chat()``: erst NACHDEM das
    Modell geantwortet hatte, die Antwort ging verloren."""
    assert Model(id="x", shutdown_date=20260101).is_retired_on(date(2099, 1, 1)) is False  # type: ignore[arg-type]
    assert Model.from_response({"id": "x", "shutdown_date": 20260101}).shutdown_date is None


@pytest.mark.parametrize(("feld", "wert", "erwartet"), [
    ("demand", "5", None), ("demand", True, None), ("demand", 3, 3),
    ("status", 1, None), ("status", "ready", "ready"),
    ("id", 42, ""), ("id", "glm-4.7", "glm-4.7"),
    ("output", "text", ()), ("output", ["text", 7], ("text",)),
    ("name", ["x"], None), ("owned_by", {"a": 1}, None),
])
def test_ein_feld_in_falscher_form_gilt_als_nicht_gesagt(feld, wert, erwartet):
    """"Jedes Feld bleibt optional: ein fehlendes ist eine Antwort, kein
    Fehler" -- und eines in falscher Form ist wie ein fehlendes. Gemessen:
    ``demand="5"`` neben einer Zahl warf ``TypeError`` beim Ordnen."""
    daten = {"id": "m", feld: wert}
    assert getattr(Model.from_response(daten), feld) == erwartet


def test_eine_gemischte_liste_laesst_sich_ordnen():
    """Der gemessene Fall selbst: ``rank_models`` ueber ``"5"`` und ``3``."""
    from edusharing.bapi.models import rank_models

    liste = [Model.from_response({"id": "a", "demand": "5", "status": "ready",
                                  "output": ["text"]}),
             Model.from_response({"id": "b", "demand": 3, "status": "ready",
                                  "output": ["text"]})]
    assert [m.id for m in rank_models(liste)] == ["b", "a"]


# --- Virtuelles Modell -----------------------------------------------------
#
# Mehrere Modelle unter einem Namen, und die Bibliothek nimmt daraus immer das
# am wenigsten ausgelastete. Nur die AcademicCloud meldet ``demand``; bei
# OpenAI ist das Feld nicht vorhanden, dort wird daraus eine Ausweichkette in
# der genannten Reihenfolge.

def test_die_wahl_faellt_innerhalb_der_genannten_modelle():
    """Ein niedriger ausgelastetes Modell ausserhalb der Auswahl gewinnt nicht."""
    modelle = [_m("a", demand=3), _m("b", demand=0), _m("c", demand=1)]
    assert pick_model(modelle, among=["a", "c"]).id == "c"


def test_ein_unbekannter_name_in_der_auswahl_faellt_auf():
    with pytest.raises(ValidationError) as info:
        pick_model([_m("a"), _m("b")], among=["a", "gibt-es-nicht"])
    assert "gibt-es-nicht" in str(info.value)


def test_auswahl_ohne_brauchbares_modell():
    modelle = [_m("a", status="loading"), _m("b", demand=0)]
    with pytest.raises(ValidationError) as info:
        pick_model(modelle, among=["a"])
    assert "a" in str(info.value)


def test_leere_auswahl_ist_ein_fehler():
    with pytest.raises(ValidationError):
        pick_model([_m("a")], among=[])


def test_ohne_auslastung_entscheidet_die_reihenfolge_der_auswahl():
    """OpenAI meldet kein ``demand`` -- dann ist die genannte Reihenfolge die
    Aussage des Aufrufers und wird respektiert."""
    modelle = [_m("zebra", demand=None), _m("alpha", demand=None)]
    assert pick_model(modelle, among=["zebra", "alpha"]).id == "zebra"


def test_prefer_und_among_zusammen_ist_ein_fehler():
    """Zwei Arten, dasselbe zu bestimmen -- da muss der Aufrufer sich festlegen."""
    with pytest.raises(ValidationError):
        pick_model([_m("a")], prefer="a", among=["a"])


# --- Wo nichts zu ranken ist ----------------------------------------------
#
# Gemessen am 31.08.2026 gegen die b-api: OpenAI meldet fuer alle 132 Modelle
# weder ``demand`` noch ``output``. Damit gilt jedes als chatfaehig und die
# Sortierung faellt auf den Namen zurueck -- die automatische Wahl griff zu
# ``babbage-002``, einem Vervollstaendigungsmodell, und der Aufruf endete nach
# drei vergeblichen Versuchen mit einer Meldung, die die Ursache nicht nennt.
#
# Alphabetisch ist keine Rangfolge. Wo es nichts zu ranken gibt, ist Raten die
# falsche Antwort: die Bibliothek kann nicht wissen, welches der 132 Modelle
# taugt, und darf es auch nicht wissen wollen -- das waere eine verdrahtete
# Konvention.

def test_ohne_jede_ranggrundlage_wird_nicht_geraten():
    ohne = [Model(id=i) for i in ("babbage-002", "gpt-5.6-luna", "dall-e-2")]
    with pytest.raises(ValidationError) as info:
        pick_model(ohne)
    # Die Meldung muss den Ausweg nennen, nicht nur den Fehlschlag.
    assert "model=" in str(info.value)
    assert "load()" in str(info.value)


def test_eine_einzige_lastangabe_genuegt_als_grundlage():
    """Sobald irgendetwas gemeldet wird, ist die Rangfolge eine Aussage."""
    gemischt = [Model(id="a"), Model(id="b", demand=0)]
    assert pick_model(gemischt).id == "b"


def test_eine_angabe_zur_ausgabeart_genuegt_ebenfalls():
    """Sie macht die Liste rankbar -- an der Reihenfolge aendert sie nichts.

    Ein Modell ohne gemeldete Ausgabeart gilt weiter als chatfaehig (das Feld
    ist dort abwesend, nicht verneint), also entscheidet wie sonst die
    Auslastung, und bei Gleichstand die ID.
    """
    gemischt = [Model(id="a"), Model(id="b", output=("text",))]
    assert pick_model(gemischt).id == "a"


def test_mit_ranggrundlage_bleibt_alles_wie_es_war():
    modelle = [_m("a", demand=3), _m("b", demand=0)]
    assert pick_model(modelle).id == "b"
