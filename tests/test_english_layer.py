"""The hand-written layer is English -- CONTRIBUTING's "Language" rule, guarded.

On 2026-09-23 German stood in ``src/`` where the refactor "English throughout
the hand-written layer" (2026-09-20) had missed it or where it was written
afterwards: a comment block, a ``__repr__``, identifiers such as ``roh`` and
``teil`` (audit MNT-23-2). Nothing noticed. This file does.

A word list, not a language detector: German function words, and the German
words this codebase's own German test modules use as names -- the habit the
slips came from. A word only counts where it stands as prose or as part of a
name; a quotation (``"..."`` or double backticks) is exempt, because quoting a
measured German query or a German test name is what an English comment should
do. The test modules themselves are not scanned: CONTRIBUTING lets them keep
the language of their file.
"""

import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: German words with no ordinary English use. Left out on purpose: ``die``,
#: ``den``, ``des``, ``am``, ``im``, ``an``, ``in``, ``so``, ``es``, ``was``,
#: ``war``, ``hat``, ``man``, ``also``, ``will``, ``kind``, ``gut``, ``art``,
#: ``rest``, ``form``, ``plan``, ``gross`` -- all of them English as well.
GERMAN = frozenset("""
    aber alle alles als auch auf bei beide beiden bereits bis dann dass das dem
    der diese diesem diesen dieser dieses doch durch eine einem einen einer
    eines erst fuer für gegen gibt hier immer jede jeder jedes kann kein keine
    keinem keinen keiner muss nach nicht nichts noch nur oder ohne schon sehr
    sich sind soll sollte ueber über und unter vom von weil wenn werden wie wird
    wurde wurden zum zur zwischen ist mit
    abgelehnt abweichung abweichungen adresse anfang antwort antworten anzahl
    anzeige aufruf aufrufe baue baum bericht beschreibung bleibt daten datei
    dateien dienst dokumente durchgereicht durchgereichten echt echte eintrag
    eintraege eltern ende erlaubt erste erwartet erzeugt fehler fehlt feld
    felder gefunden geaendert gefragt gekuerzt gelesen gemeldet genannt gesagt
    gesamt gesamtzahl gesehen gesendet geschrieben gespeichert herkunft inhalt
    kinder klasse klein knoten kopie kopien kurzbeschreibung leer leere liefert
    liste meldung modell modelle nachschlag neu neue nennt offen ordner paare
    pfad pfade pruefung quelle quellen rechte roh sagt sammlung sammlungen
    schluessel seite seiten steht suche synchronisiere teil teile titel treffer
    typen unbrauchbare verwaist vorlage vorlagen wert werte wurzel zahl zahlen
    zeile zeilen ziel zweite
""".split())

#: Capitalised only: "die" is an English verb, "Die" opens a German sentence.
GERMAN_CAPITALISED = frozenset({"Die"})

#: What is scanned, relative to the repository root.
SCOPES = ("src/edusharing",)

#: German that is data, not prose -- each with the reason it stays.
ALLOWED_FILES = {
    "src/edusharing/language.py":
        "the German language profile: its stopwords and synonyms are the data",
}
ALLOWED_TEXT = {
    ("src/edusharing/flows/rerank.py", "element wurde gelöscht"):
        "the placeholder text edu-sharing itself writes into a deleted node",
    ("src/edusharing/skills_markdown.py", "[**Titel**](<Quelle>)"):
        "the block format as the editorial team writes it, quoted as an example",
    ("src/edusharing/skills_markdown.py", "[Titel]("):
        "the same example block",
}

_QUOTED = re.compile(r'``.*?``|"[^"]*"', re.DOTALL)
_STRING = re.compile(r'^[A-Za-z]*("""|\'\'\'|"|\')(.*)\1$', re.DOTALL)
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß]+")
_MIDDLE = {getattr(tokenize, name) for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")
           if hasattr(tokenize, name)}


def _german(text: str) -> list[str]:
    prose = _QUOTED.sub(" ", text)
    return sorted({w for w in _WORD.findall(prose)
                   if w.lower() in GERMAN or w in GERMAN_CAPITALISED})


def _python_findings(source: str, label: str) -> list[str]:
    found = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            kind, words = "comment", _german(token.string)
        elif token.type == tokenize.STRING:
            literal = _STRING.match(token.string)
            text = literal.group(2) if literal else token.string
            for path, snippet in ALLOWED_TEXT:
                if path == label:
                    text = text.replace(snippet, " ")
            kind, words = "text", _german(text)
        elif token.type in _MIDDLE:
            kind, words = "text", _german(token.string)
        elif token.type == tokenize.NAME:
            parts = re.split(r"[_\d]+", token.string)
            kind, words = "name", sorted({p for p in parts if p.lower() in GERMAN})
        else:
            continue
        if words:
            found.append(f"{label}:{token.start[0]} {kind}: {' '.join(words)}")
    return found


def _files() -> list[tuple[Path, str]]:
    found = []
    for scope in SCOPES:
        for path in sorted((ROOT / scope).rglob("*")):
            label = path.relative_to(ROOT).as_posix()
            if ("_generated" in path.parts or "__pycache__" in path.parts
                    or label in ALLOWED_FILES or not path.is_file()):
                continue
            found.append((path, label))
    return found


def test_the_hand_written_layer_is_english():
    findings = [
        hit
        for path, label in _files() if path.suffix == ".py"
        for hit in _python_findings(path.read_text(encoding="utf-8"), label)
    ]
    assert findings == [], (
        "German in the English layer (CONTRIBUTING, 'Language') -- translate "
        "it, or quote it if it is a measured value:\n" + "\n".join(findings))


def test_the_guard_sees_german_and_leaves_quotations_alone():
    """A scan that finds nothing proves nothing unless it can find something."""
    sample = (
        "# Erst lesen, dann merken\n"
        "roh = 1\n"
        'text = f"{a} von {b}"\n'
        "# measured: \"Ich suche ein Arbeitsblatt zur Bruchrechnung\"\n"
        "# ``test_eine_sitzung_mit_anmeldung`` holds it open\n"
        "# the loop may die here\n"
        "# Die Wache\n"
    )
    assert _python_findings(sample, "s.py") == [
        "s.py:1 comment: Erst dann",
        "s.py:2 name: roh",
        "s.py:3 text: von",
        "s.py:7 comment: Die",
    ]


def test_an_allowed_quotation_exempts_itself_and_nothing_beside_it():
    source = '_MARKER = "element wurde gelöscht"\nNOTE = "element wurde gelöscht, und mehr"\n'
    assert _python_findings(source, "src/edusharing/flows/rerank.py") == [
        "src/edusharing/flows/rerank.py:2 text: und"]
