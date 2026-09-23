"""Welche Rumpfform -- was in die Anfrage gehoert. Ohne Netz.

Alle Erwartungen stammen aus Messungen gegen die b-api (Staging). Die
Eigenheiten sind nicht optional: wer sie ignoriert, bekommt HTTP 400 oder
wartet das Sieben- bis Neunfache. Die Modellwahl steht in
``test_bapi_models.py``.
"""

import pytest

from edusharing.bapi.body import build_body, read_answer
from edusharing.errors import ValidationError

# --- Request-Bau -----------------------------------------------------------


def test_normales_modell_bekommt_max_tokens():
    body = build_body("glm-4.7", [{"role": "user", "content": "hi"}], max_tokens=100)
    assert body["max_tokens"] == 100
    assert "temperature" in body
    assert "max_completion_tokens" not in body


@pytest.mark.parametrize("mid", ["gpt-5.6-luna", "gpt-5-mini", "o1-preview", "o3", "o4-mini"])
def test_gpt5_und_o_serie_brauchen_max_completion_tokens(mid):
    """Gemessen: sonst HTTP 400. Und temperature lehnen sie ebenfalls ab."""
    body = build_body(mid, [{"role": "user", "content": "hi"}], max_tokens=100)
    assert body["max_completion_tokens"] == 100
    assert "max_tokens" not in body
    assert "temperature" not in body


def test_qwen3_bekommt_das_denken_abgeschaltet():
    """Gemessen Faktor 7 bis 9: qwen3.6-35b-a3b brauchte 17,33 s mit Denken
    und 1,96 s ohne. '/no_think' im Prompt wirkt nicht -- das ist Qwen2.5."""
    body = build_body("qwen3.6-35b-a3b", [{"role": "user", "content": "hi"}])
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_mistral_bekommt_das_flag_nicht():
    """Gemessen: 400 'chat_template is not supported for Mistral tokenizers'."""
    body = build_body("mistral-medium-3.5-128b", [{"role": "user", "content": "hi"}])
    assert "chat_template_kwargs" not in body


def test_denken_laesst_sich_erzwingen():
    body = build_body("qwen3.6-35b-a3b", [{"role": "user", "content": "hi"}], thinking=True)
    assert "chat_template_kwargs" not in body


def test_streaming_verlangt_die_verbrauchsangabe():
    body = build_body("glm-4.7", [{"role": "user", "content": "hi"}], stream=True)
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


# --- Antwort auslesen ------------------------------------------------------

def test_antworttext_wird_gelesen():
    antwort = {"choices": [{"message": {"content": "Die Antwort"}}]}
    assert read_answer(antwort) == "Die Antwort"


def test_reasoning_faengt_ein_aufgebrauchtes_budget_auf():
    """Gemessen: Reasoning-Modelle zaehlen ihr Denken mit. Ist das Budget
    aufgebraucht, kommt content: null und der Text steht in reasoning --
    qwen3.6-35b-a3b produzierte einmal 1.500 Tokens reines Reasoning ohne ein
    Zeichen Antwort."""
    antwort = {"choices": [{"message": {"content": None, "reasoning": "Gedanken"},
                            "finish_reason": "length"}]}
    assert read_answer(antwort) == "Gedanken"


def test_leere_antwort_ergibt_leeren_text():
    assert read_answer({"choices": []}) == ""
    assert read_answer({}) == ""


# --- reasoning_effort und verbosity ----------------------------------------
#
# Gemessen am 31.08.2026 gegen die b-api (Staging):
#
#   gpt-5.6-luna    ohne Parameter   completion=32  reasoning=14
#   gpt-5.6-luna    effort=low       completion=11  reasoning=0     <- wirkt
#   gpt-5.6-luna    effort=high      completion=35  reasoning=17
#   gpt-5-nano      effort=low       200
#   gpt-4o-mini     effort=low       400 Unrecognized request argument
#   gpt-3.5-turbo   effort=low       400 Unrecognized request argument
#   gpt-4o-mini     verbosity=low    400 does not support 'low' ... only 'medium'
#   qwen3.5-122b    effort=low/high  200, aber completion identisch -> ignoriert
#
# Daraus die Regel: low ist die Vorgabe, weil sie messbar Denk-Tokens spart.
# Wo das Modell sie nicht kennt, entfaellt sie stillschweigend -- eine Vorgabe
# darf das. Ein ausdruecklich uebergebener Wert darf es nicht: still verworfen
# saehe eine Antwort mit hohem Aufwand genauso aus wie eine mit niedrigem.

def test_vorgabe_low_landet_im_rumpf_wo_das_modell_sie_kennt():
    body = build_body("gpt-5.6-luna", [{"role": "user", "content": "x"}])
    assert body["reasoning_effort"] == "low"
    assert body["verbosity"] == "low"


def test_vorgabe_entfaellt_still_wo_das_modell_sie_nicht_kennt():
    """gpt-4o-mini antwortet sonst mit 400."""
    body = build_body("gpt-4o-mini", [{"role": "user", "content": "x"}])
    assert "reasoning_effort" not in body
    assert "verbosity" not in body


def test_vorgabe_entfaellt_auch_bei_der_academiccloud():
    """Dort wird der Parameter angenommen und ignoriert -- also nicht senden."""
    body = build_body("qwen3.5-122b-a10b", [{"role": "user", "content": "x"}])
    assert "reasoning_effort" not in body


@pytest.mark.parametrize("feld", ["reasoning_effort", "verbosity"])
def test_ausdruecklicher_wunsch_wird_nicht_still_verworfen(feld):
    """Der Kern der Regel."""
    with pytest.raises(ValidationError) as info:
        build_body("gpt-4o-mini", [{"role": "user", "content": "x"}], **{feld: "high"})
    assert "gpt-4o-mini" in str(info.value)
    assert feld in str(info.value)


def test_ausdruecklicher_wunsch_wird_uebernommen_wo_er_geht():
    body = build_body("gpt-5.6-luna", [{"role": "user", "content": "x"}],
                      reasoning_effort="high", verbosity="medium")
    assert body["reasoning_effort"] == "high"
    assert body["verbosity"] == "medium"


@pytest.mark.parametrize("modell", ["gpt-5.6-luna", "gpt-4o-mini"])
def test_none_heisst_gar_nicht_senden(modell):
    body = build_body(modell, [{"role": "user", "content": "x"}],
                      reasoning_effort=None, verbosity=None)
    assert "reasoning_effort" not in body
    assert "verbosity" not in body
