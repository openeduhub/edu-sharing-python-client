"""Die Code-Bloecke in den Dokumenten laufen gegen die echte Oberflaeche.

Die vierte Doku-Wache, und die letzte Luecke der drei anderen.
``test_docs_complete`` fragt, ob jeder oeffentliche Name **vorkommt**;
``test_docs_inventories``, ob die Verzeichnisse **stimmen**;
``test_docstrings``, ob die Erklaerung **da** ist und ihre Verweise auf etwas
zeigen. Keine fragt, ob der Code, den jemand aus einem Dokument **kopiert**,
ueberhaupt laeuft.

Die Beispiele in ``docs/examples`` werden ausgefuehrt (``test_live_examples``).
Die Bloecke in README, FLOWS, REFERENCE und SKILL fuehrt niemand aus -- und
das ist die groessere Flaeche: ueber tausend Attributzugriffe.

Gemessen am 09.09.2026, beim ersten Lauf dieser Wache:

* ``await repo.resolve(...)`` in beiden READMEs -- die **synchrone** Fassade
  hat ``resolve``, die asynchrone nicht; dort heisst es ``repo.vocab.resolve``.
  Ein Aufruf, der kopiert einen ``AttributeError`` wirft.
* ein Block in FLOWS, als ``python`` ausgezeichnet, der HTTP enthaelt.
* ein Block in REFERENCE, der eine Zeichenkette ueber zwei Zeilen offen laesst.

Zwei Fragen, mehr nicht: parst der Block, und gibt es, was er aufruft. Ob ein
Aufruf mit seinen Argumenten auch **bindet**, fragt ``test_docs_signatures``;
ob die **Werte** darin stimmen, ``test_docs_values``; ob jede Option
dokumentiert ist, ``test_docs_options``. Die Wurzeln, ``_bloecke`` und
``_kette`` stehen hier und werden von dort geholt.
"""

import ast
import functools
import importlib
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from edusharing import (
    AsyncRepository,
    Repository,
)
from edusharing._sync import SyncNode
from edusharing.bapi import BapiTemplates, BildungsAPI
from edusharing.childobjects import ChildObjects
from edusharing.collections import Collections
from edusharing.content import NodeContent
from edusharing.flows import Flows
from edusharing.metadata import MetadataCatalog
from edusharing.metadata_agent import MetadataAgent
from edusharing.nodes import Node, Nodes
from edusharing.people import People
from edusharing.relations import Relations
from edusharing.search import Search
from edusharing.skills import Skills
from edusharing.vocab import Vocabulary

WURZEL = Path(__file__).resolve().parent.parent

#: Jedes Dokument, dessen Bloecke jemand kopieren koennte.
DOKUMENTE = [
    "README.md", "README.de.md",
    "docs/FLOWS.md", "docs/FLOWS.de.md",
    "docs/REFERENCE.md", "docs/REFERENCE.de.md",
    "docs/ARCHITECTURE.md", "docs/ARCHITECTURE.de.md",
    "docs/B-API-ROUTING.de.md",
    ".claude/skills/edu-sharing-python/SKILL.md",
    ".claude/skills/edu-sharing-python/SKILL.de.md",
    ".claude/skills/edu-sharing-python/reference/TRAPS.md",
    ".claude/skills/edu-sharing-python/reference/TRAPS.de.md",
]

#: Was hier steht, ist eine bewusste Ausnahme mit Begruendung, kein Rueckstand.
#: Der Schluessel ist ``(Datei, erste Zeile des Blocks)`` -- eine Blocknummer
#: verschoebe sich beim naechsten eingefuegten Absatz.
NICHT_PYTHON = {
    # ARCHITECTURE zeigt, was der Generator aus der unveraenderten
    # Spezifikation macht: ein ``def`` mit einem Parameter ohne Vorgabe hinter
    # einem mit. Dass es **nicht** parst, ist die Aussage des Absatzes.
    ("docs/ARCHITECTURE.md", "def _get_kwargs("),
    ("docs/ARCHITECTURE.de.md", "def _get_kwargs("),
}

_BLOCK = re.compile(r"```(?:python|py)\n(.*?)```", re.S)

#: Variablenname -> Klasse. Nur, was eindeutig ist: ``kind`` etwa steht in der
#: README fuer eine Inhaltsart und nicht fuer ein Kindobjekt. ``api`` und
#: ``agent`` seit dem 11.09.2026 -- gemessen stehen sie in jedem Block fuer
#: ``BildungsAPI`` und ``MetadataAgent``; ``extraction`` nicht, es fehlt hier.
_WURZELN_ASYNC = {"repo": AsyncRepository, "node": Node, "knoten": Node,
                  "templates": BapiTemplates, "api": BildungsAPI,
                  "agent": MetadataAgent}

#: Synchron gilt ``Repository`` selbst -- die Fassade ist ausgeschrieben und
#: damit genau pruefbar (``resolve`` gibt es dort und asynchron nicht).
#: Fuer den Knoten gilt ``Node``: ``SyncNode`` reicht jeden Lesezugriff per
#: ``__getattr__`` weiter, und was eine Klasse dynamisch aufloest, kann
#: ``hasattr`` nicht sehen -- so gemeldet stuenden ``node.get``,
#: ``node.get_all`` und ``node.properties`` faelschlich als Fehler da
#: (Messung 09.09.2026).
_WURZELN_SYNC = {"repo": Repository, "node": Node, "knoten": Node,
                 "templates": BapiTemplates, "api": BildungsAPI,
                 "agent": MetadataAgent}

#: Wo ein Attribut selbst wieder eine Oberflaeche ist.
_WEITER = {
    (AsyncRepository, "flows"): Flows,
    (AsyncRepository, "skills"): Skills,
    (AsyncRepository, "nodes"): Nodes,
    (AsyncRepository, "collections"): Collections,
    (AsyncRepository, "people"): People,
    (AsyncRepository, "relations"): Relations,
    (AsyncRepository, "vocab"): Vocabulary,
    (AsyncRepository, "metadata"): MetadataCatalog,
    (Repository, "metadata"): MetadataCatalog,
    (AsyncRepository, "searcher"): Search,
    (Node, "content"): NodeContent,
    (Node, "children"): ChildObjects,
    # Blockierend ``SyncFlows``: Name fuer Name dieselben Ablaeufe, jeder reicht
    # an ``Flows`` weiter. Nur hier gleichgesetzt -- ``SyncTransport`` etwa ist
    # absichtlich schmaler als ``Transport`` (kein ``aclose``), dort waere die
    # asynchrone Flaeche zu nachsichtig.
    (Repository, "flows"): Flows,
}


def _bloecke(rel: str) -> list[tuple[str, str]]:
    """Jeder ``python``-Block einer Datei, mit seiner ersten Zeile als Namen."""
    text = (WURZEL / rel).read_text(encoding="utf-8")
    gefunden = []
    for quelle in _BLOCK.findall(text):
        zeilen = [z for z in quelle.splitlines() if z.strip()]
        gefunden.append((zeilen[0].strip() if zeilen else "", quelle))
    return gefunden


def _kette(knoten: ast.AST) -> list[str] | None:
    """``a.b.c`` -> ``['a', 'b', 'c']``; alles andere -> ``None``."""
    teile = []
    while isinstance(knoten, ast.Attribute):
        teile.append(knoten.attr)
        knoten = knoten.value
    if not isinstance(knoten, ast.Name):
        return None
    teile.append(knoten.id)
    return list(reversed(teile))


@functools.cache
def _instanzattribute(klasse: type) -> frozenset[str]:
    """Was ``__init__`` als ``self.x`` setzt -- auch geerbt.

    ``hasattr`` fragt die Klasse, und dort steht ``api.last_model`` nicht:
    ``BildungsAPI.__init__`` setzt es erst am Objekt.
    """
    gefunden: set[str] = set()
    for k in klasse.__mro__:
        init = vars(k).get("__init__")
        if not inspect.isfunction(init):
            continue
        try:
            baum = ast.parse(textwrap.dedent(inspect.getsource(init)))
        except (OSError, TypeError):   # ohne Quelltext: nichts zu lesen
            continue
        for knoten in ast.walk(baum):
            ziele = (knoten.targets if isinstance(knoten, ast.Assign)
                     else [knoten.target] if isinstance(knoten, ast.AnnAssign) else [])
            gefunden.update(z.attr for z in ziele
                            if isinstance(z, ast.Attribute) and isinstance(z.value, ast.Name)
                            and z.value.id == "self")
    return frozenset(gefunden)


def _unbekannte_aufrufe(quelle: str, baum: ast.AST) -> list[str]:
    """Jeder ``wurzel.a.b``, den es an der Oberflaeche nicht gibt.

    Welche Fassade gilt, sagt der Block selbst: steht ein ``await`` darin, ist
    er asynchron. Der Unterschied ist keine Feinheit -- ``resolve`` gibt es
    an der synchronen Fassade und an der asynchronen nicht.
    """
    wurzeln = _WURZELN_ASYNC if "await " in quelle else _WURZELN_SYNC
    fehlend = []
    for k in ast.walk(baum):
        if not isinstance(k, ast.Attribute):
            continue
        teile = _kette(k)
        if not teile or teile[0] not in wurzeln:
            continue
        klasse: type | None = wurzeln[teile[0]]
        pfad = teile[0]
        for name in teile[1:]:
            if klasse is None:
                break            # hinter einem unbekannten Rueckgabewert
            if not hasattr(klasse, name) and name not in _instanzattribute(klasse):
                fehlend.append(f"{pfad}.{name}")
                break
            pfad = f"{pfad}.{name}"
            klasse = _WEITER.get((klasse, name))
    return fehlend


def _gibt_es(modul: str, name: str | None = None) -> bool:
    """Ob ``import modul`` (und darin ``name``, als Wert oder Untermodul) gelingt."""
    try:
        geladen = importlib.import_module(modul)
    except ImportError:
        return False
    if name is None or hasattr(geladen, name):
        return True
    try:
        importlib.import_module(f"{modul}.{name}")
    except ImportError:
        return False
    return True


def _unbekannte_importe(baum: ast.AST) -> list[str]:
    """Jeder Import aus ``edusharing``, den es nicht gibt."""
    fehlend = []
    for k in ast.walk(baum):
        if isinstance(k, ast.Import):
            fehlend += [f"import {a.name}" for a in k.names
                        if a.name.split(".")[0] == "edusharing" and not _gibt_es(a.name)]
        elif (isinstance(k, ast.ImportFrom) and not k.level and k.module
              and k.module.split(".")[0] == "edusharing"):
            if not _gibt_es(k.module):
                fehlend.append(f"from {k.module} import ...")
                continue
            fehlend += [f"from {k.module} import {a.name}" for a in k.names
                        if a.name != "*" and not _gibt_es(k.module, a.name)]
    return fehlend


def _nicht_parsende(rel: str, bloecke: list[tuple[str, str]]) -> list[str]:
    """Welche Bloecke nicht parsen -- getrennt, damit die Gegenprobe sie
    fuettern kann.

    Ohne die Trennung ist die Wache still gruen, sobald alle Bloecke parsen:
    ihren ``except``-Zweig zu entfernen faellt dann niemandem auf.
    """
    kaputt = []
    for erste, quelle in bloecke:
        if (rel, erste) in NICHT_PYTHON:
            continue
        try:
            ast.parse(quelle)
        except SyntaxError as fehler:
            kaputt.append(f"{erste!r}: {fehler.msg}")
    return kaputt


@pytest.mark.parametrize("rel", DOKUMENTE)
def test_jeder_codeblock_parst(rel: str):
    """Wer einen Block kopiert, bekommt keinen Syntaxfehler.

    Ein Block, der als ``python`` ausgezeichnet ist und keiner ist, ist zweimal
    falsch: die Hervorhebung stimmt nicht, und wer ihn nimmt, kann ihn nicht
    ausfuehren.
    """
    kaputt = _nicht_parsende(rel, _bloecke(rel))
    assert not kaputt, (
        f"{rel}: Block als ``python`` ausgezeichnet, parst aber nicht -- "
        "entweder die Auszeichnung aendern (``text``) oder in NICHT_PYTHON "
        "eintragen, mit dem Grund:\n  " + "\n  ".join(kaputt))


@pytest.mark.parametrize("rel", DOKUMENTE)
def test_jeder_codeblock_ruft_nur_vorhandenes(rel: str):
    """Kopierter Code darf nicht am ersten Aufruf scheitern."""
    fehlend = []
    for erste, quelle in _bloecke(rel):
        if (rel, erste) in NICHT_PYTHON:
            continue
        try:
            baum = ast.parse(quelle)
        except SyntaxError:
            continue             # sagt der andere Test
        fehlend.extend(_unbekannte_aufrufe(quelle, baum))
    assert not fehlend, (
        f"{rel}: das Dokument ruft, was es nicht gibt:\n  "
        + "\n  ".join(sorted(set(fehlend))))


def test_die_parsewache_kann_rot_werden():
    """Gefuettert statt gehofft: ein Block, der nicht parst, muss auffallen
    -- und die Ausnahme muss ihn durchlassen."""
    bloecke = [("gut = 1", "gut = 1\n"), ("def kaputt(", "def kaputt(\n")]
    assert _nicht_parsende("egal.md", bloecke) == [
        "'def kaputt(': '(' was never closed"]
    assert _nicht_parsende("docs/ARCHITECTURE.md", [
        ("def _get_kwargs(", "def _get_kwargs(\n")]) == []


def test_die_codewache_sieht_ueberhaupt_etwas():
    """Eine Wache ohne Fund ist still gruen -- also wird sie gefuettert."""
    gut = "await repo.flows.search('x')\nawait node.content.download()"
    schlecht = "await repo.gibt_es_nicht()\nawait node.content.auch_nicht()"
    assert _unbekannte_aufrufe(gut, ast.parse(gut)) == []
    assert _unbekannte_aufrufe(schlecht, ast.parse(schlecht)) == [
        "repo.gibt_es_nicht", "node.content.auch_nicht"]


def test_die_codewache_prueft_den_template_modus():
    """``templates`` steht in den Dokumenten fuer ``BapiTemplates`` (seit dem
    11.09.2026) -- ein Aufruf, den es dort nicht gibt, muss auffallen."""
    gut = "await templates.chat(chain, context_node_id=k)"
    schlecht = "await templates.template_chat(chain)"
    assert _unbekannte_aufrufe(gut, ast.parse(gut)) == []
    assert _unbekannte_aufrufe(schlecht, ast.parse(schlecht)) == [
        "templates.template_chat"]


def test_die_codewache_kennt_was_der_konstruktor_setzt():
    """``api.last_model`` sagt, welches Modell geantwortet hat -- gesetzt in
    ``BildungsAPI.__init__``, nicht an der Klasse. ``hasattr`` sieht es nicht."""
    gut = "await api.chat('Hallo')\nprint(api.last_model)"
    schlecht = "print(api.letztes_modell)"
    assert _unbekannte_aufrufe(gut, ast.parse(gut)) == []
    assert _unbekannte_aufrufe(schlecht, ast.parse(schlecht)) == ["api.letztes_modell"]


def test_die_importwache_sieht_ein_modul_das_es_nicht_gibt():
    """``from edusharing.flows.ranking import query_terms`` stand bis zum
    11.09.2026 in REFERENCE -- das Modul heisst ``edusharing.ranking``."""
    gut = ("from edusharing import GERMAN, Repository\n"
           "from edusharing.ranking import query_terms\n"
           "from edusharing.agent import as_untrusted\nimport edusharing.bapi\n")
    schlecht = ("from edusharing.flows.ranking import query_terms\n"
                "from edusharing import Client\nimport edusharing.gibt_es_nicht\n")
    assert _unbekannte_importe(ast.parse(gut)) == []
    assert _unbekannte_importe(ast.parse(schlecht)) == [
        "from edusharing.flows.ranking import ...", "from edusharing import Client",
        "import edusharing.gibt_es_nicht"]


@pytest.mark.parametrize("rel", DOKUMENTE)
def test_jeder_import_gibt_es(rel: str):
    """Die erste Zeile, die kopierter Code ausfuehrt, ist der Import."""
    fehlend = []
    for erste, quelle in _bloecke(rel):
        if (rel, erste) in NICHT_PYTHON:
            continue
        try:
            fehlend.extend(_unbekannte_importe(ast.parse(quelle)))
        except SyntaxError:
            continue             # sagt der Parse-Test
    assert not fehlend, f"{rel} importiert, was es nicht gibt:\n  " + "\n  ".join(fehlend)


def test_die_fassaden_loesen_auf_wie_angenommen():
    """Woran die Zuordnung oben haengt.

    ``Repository`` ist ausgeschrieben, also genau pruefbar. ``SyncNode``
    delegiert -- bekaeme es eines Tages seine eigenen Lesezugriffe oder
    verloere die Delegation, waere die Zuordnung still falsch.
    """
    assert "__getattr__" not in vars(Repository), (
        "``Repository`` loest nicht mehr statisch auf -- dann ist die exakte "
        "Pruefung gegen es zu streng")
    assert "__getattr__" in vars(SyncNode), (
        "``SyncNode`` delegiert nicht mehr -- dann gilt fuer synchrone "
        "Bloecke wieder seine eigene Flaeche")


def test_die_codewache_unterscheidet_die_fassaden():
    """``resolve`` gibt es synchron und asynchron nicht -- genau daran haing
    der Befund vom 09.09.2026."""
    asynchron = "uri = await repo.resolve('a', 'b')"
    synchron = "uri = repo.resolve('a', 'b')"
    assert _unbekannte_aufrufe(asynchron, ast.parse(asynchron)) == ["repo.resolve"]
    assert _unbekannte_aufrufe(synchron, ast.parse(synchron)) == []


def test_die_ausnahmen_gibt_es_noch():
    """Eine Ausnahme fuer einen Block, den es nicht mehr gibt, ist eine
    Karteileiche -- und die naechste Person haelt sie fuer eine Regel."""
    vorhanden = {(rel, erste) for rel in DOKUMENTE for erste, _ in _bloecke(rel)}
    verwaist = sorted(NICHT_PYTHON - vorhanden)
    assert not verwaist, f"in NICHT_PYTHON, aber nicht mehr im Dokument: {verwaist}"


# --- "async only" in der Prosa (11.09.2026) ------------------------------
#
# Die Wachen oben lesen Code. Eine Tabellenzeile, die eine Flaeche "async
# only" nennt, ist kein Code -- und genau so eine hat den Fix vom 10.09.2026
# ueberlebt: vier Zeilen je Sprache nannten Flaechen asynchron, die ab da
# blockierten. Ein Agent, der den Skill liest, haette sie auf dem
# blockierenden Repository gemieden.
#
# Die Pruefung glaubt der Aussage nicht, sie misst sie: wer "async only" sagt,
# muss eine Flaeche meinen, die auf dem blockierenden Repository wirklich noch
# Koroutinen hergibt.

_NUR_ASYNC = re.compile(r"`repo\.(\w+)`\s*—\s*\*\*(?:async only|nur asynchron)\*\*")


def _ist_nur_asynchron(name: str) -> bool:
    """Gibt ``Repository`` fuer diese Flaeche noch Koroutinen her?"""
    repo = Repository("https://repo.test/edu-sharing")
    try:
        flaeche = getattr(repo, name, None)
        if flaeche is None:
            return True
        return any(
            inspect.iscoroutinefunction(getattr(flaeche, m, None))
            for m in dir(flaeche) if not m.startswith("_"))
    finally:
        repo.close()


@pytest.mark.parametrize("rel", [
    ".claude/skills/edu-sharing-python/SKILL.md",
    ".claude/skills/edu-sharing-python/SKILL.de.md",
    ".claude/skills/edu-sharing-python/reference/TRAPS.md",
    ".claude/skills/edu-sharing-python/reference/TRAPS.de.md",
    "docs/REFERENCE.md", "docs/REFERENCE.de.md",
    "docs/FLOWS.md", "docs/FLOWS.de.md",
    "README.md", "README.de.md",
])
def test_was_als_nur_asynchron_gilt_ist_es_auch(rel: str):
    text = (WURZEL / rel).read_text(encoding="utf-8")
    falsch = [name for name in _NUR_ASYNC.findall(text)
              if not _ist_nur_asynchron(name)]
    assert not falsch, (
        f"{rel} nennt diese Flaechen 'async only', die auf dem blockierenden "
        f"Repository blockieren: {', '.join('repo.' + n for n in falsch)}")


def test_die_nur_asynchron_wache_erkennt_eine_echte_ausnahme():
    """Die Gegenprobe: die Pruefung darf nicht jede Aussage verwerfen. Ein
    Name, den das blockierende Repository gar nicht hat, ist nur asynchron --
    oder gar nicht da; beides verbietet die Aussage nicht."""
    assert _ist_nur_asynchron("gibt_es_nicht") is True
    assert _ist_nur_asynchron("vocab") is False
