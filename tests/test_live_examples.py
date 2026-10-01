"""Die Beispiele aus ``docs/examples``, jedes als eigener Testfall.

Sie liefen bisher nur von Hand. Ein Beispiel ist aber ausfuehrbare
Dokumentation, und Dokumentation, die niemand ausfuehrt, verrottet unbemerkt:
``12_flow_place.py`` brach beim A3-Umbau, weil ``placement()`` seither eine
Teilantwort liefern darf statt zu werfen. Aufgefallen ist das beim
Ausprobieren von Hand -- die Suite hatte dazu nichts zu sagen.

    uv run pytest -m live  tests/test_live_examples.py
    uv run pytest -m write tests/test_live_examples.py

Geprueft wird der **Exitcode**, nicht die Ausgabe. Was ein Beispiel druckt,
haengt am Bestand der Instanz und aendert sich taeglich; dass es ueberhaupt
durchlaeuft, haengt an der Bibliothek.

**Wenn die Zeitgrenze zuschlaegt**, wird der Unterprozess abgeschossen, und sein
``finally`` laeuft dann nicht mehr. Ein schreibendes Beispiel laesst in dem Fall
seinen Wegwerf-Ordner auf der Instanz stehen -- selbst angelegt, aber eben
liegengeblieben. Deshalb ist ``ZEITGRENZE`` grosszuegig gesetzt; die Messung
dahinter steht dort.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
BEISPIELE = WURZEL / "docs" / "examples"

#: Lesend. Laufen anonym; Zugangsdaten weiten hoechstens aus, was sie sehen.
LESEND = frozenset({
    "01_connect.py",
    "02_search.py",
    "04_agent_blocks.py",
    "05_flow_search.py",
    "08_flow_rerank.py",
    "12_flow_place.py",
    "13_flow_tree.py",
    "14_flow_page.py",
    "15_full_text.py",
    "18_video_recommendation.py",
    "19_collection_audit.py",
    "20_provider_load.py",
    "21_skills.py",
    "22_bapi_templates.py",
    "24_generic_metadata.py",
    "25_prepare_context.py",
    "26_extract_page.py",
    "27_bapi_router.py",
})

#: Legen etwas an -- jedes einen eigenen Wegwerf-Ordner, den es selbst wieder
#: raeumt. Brauchen Zugangsdaten und tragen deshalb den write-Marker.
SCHREIBEND = frozenset({
    "03_write.py",
    "06_flow_create.py",
    "07_flow_collection.py",
    "09_flow_browse.py",
    "10_two_levels.py",
    "11_publish.py",
    "16_editorial.py",
    "17_flow_belonging.py",
    "23_ai_suggestions.py",
})

#: Grosszuegig, damit ein langsames Netz kein Fehlschlag ist -- ein Zuschlagen
#: der Grenze kostet einen liegengebliebenen Wegwerf-Ordner (siehe oben).
#: Zweimal gemessen gegen die Staging, und die zweite Messung ist der Grund,
#: warum die Zahl hier steht statt geraten zu werden::
#:
#:                      28.08.   29.08.
#:     04_agent_blocks   17,1 s   76,1 s   <- jetzt das langsamste
#:     15_full_text      20,4 s   40,9 s
#:     11_publish        14,5 s   19,4 s
#:     17_flow_belonging      -   10,7 s   <- neu
#:     01_connect         1,4 s    2,2 s
#:     ---------------------------------
#:     alle zusammen      2:19     4:07
#:
#: Der teuerste Einzelfall hat sich mehr als vervierfacht, ohne dass sich an
#: den Beispielen etwas geaendert haette -- die Staging antwortet an manchen
#: Tagen langsamer. Die Grenze liegt damit noch rund dreimal darueber statt
#: zwoelfmal. Sie bleibt, wo sie ist; wer sie senken will, misst vorher.
ZEITGRENZE = 240.0

_URL = bool(os.environ.get("EDU_SHARING_URL"))
_ANMELDUNG = _URL and bool(os.environ.get("EDU_SHARING_USER"))


def _faelle(namen: frozenset[str]) -> list:
    return [pytest.param(BEISPIELE / n, id=n[:-3]) for n in sorted(namen)]


def _lauf(pfad: Path) -> subprocess.CompletedProcess:
    """So starten, wie der eigene Docstring des Beispiels es vorschreibt."""
    return subprocess.run(
        [sys.executable, str(pfad.relative_to(WURZEL))],
        cwd=WURZEL, capture_output=True, timeout=ZEITGRENZE, check=False,
    )


def _bericht(pfad: Path, lauf: subprocess.CompletedProcess) -> str:
    """Die letzten stderr-Zeilen, damit der Fehlschlag ohne Nachlauf lesbar ist."""
    zeilen = lauf.stderr.decode("utf-8", "replace").strip().splitlines()
    return (f"{pfad.name} endete mit Exitcode {lauf.returncode}; stderr: "
            + " | ".join(zeilen[-5:] or ["(leer)"]))


def test_jedes_beispiel_ist_eingeordnet():
    """Ein neues Beispiel muss lesend oder schreibend genannt werden.

    Ohne diese Pruefung liefe ein neues schreibendes Beispiel unter ``-m live``
    ohne Zugangsdaten und schluege aus dem falschen Grund fehl -- oder es liefe
    gar nicht mit und niemand merkte es. Dieser Test braucht kein Netz und
    laeuft deshalb in der Vorgabe-Suite mit.
    """
    auf_platte = {p.name for p in BEISPIELE.glob("*.py")}
    assert auf_platte, f"keine Beispiele unter {BEISPIELE}"
    genannt = LESEND | SCHREIBEND
    assert genannt == auf_platte, (
        f"nur auf Platte: {sorted(auf_platte - genannt)}; "
        f"nur in der Liste: {sorted(genannt - auf_platte)}"
    )


@pytest.mark.live
@pytest.mark.skipif(not _URL, reason="EDU_SHARING_URL nicht gesetzt")
@pytest.mark.parametrize("pfad", _faelle(LESEND))
def test_lesendes_beispiel_laeuft_durch(pfad: Path):
    lauf = _lauf(pfad)
    assert lauf.returncode == 0, _bericht(pfad, lauf)


@pytest.mark.write
@pytest.mark.skipif(not _ANMELDUNG, reason="EDU_SHARING_URL/_USER nicht gesetzt")
@pytest.mark.parametrize("pfad", _faelle(SCHREIBEND))
def test_schreibendes_beispiel_laeuft_durch(pfad: Path):
    lauf = _lauf(pfad)
    assert lauf.returncode == 0, _bericht(pfad, lauf)
