"""Der Skill traegt auch ausserhalb dieses Repositoriums.

Wer ``.claude/skills/edu-sharing-python`` nutzt, kopiert den Ordner -- nach
``~/.claude/skills/``, nach ``~/.agents/skills/`` oder als ZIP zu claude.ai.
Bis zum 11.09.2026 verwies der Skill fuer jede Einzelheit nach
``../../../docs/REFERENCE.md``; ausserhalb des Repositoriums zeigt das ins
Leere, und ein Modell raet dann die Signaturen.

Deshalb liegen die Nachschlagewerke **im** Skill-Ordner, unter ``reference/``:
Kopien von REFERENCE, FLOWS (je beide Sprachen) und aller Beispiele.
Kopien, nicht Neufassungen -- eine Quelle je Inhalt. ``scripts/sync_skill.py``
stellt sie her; dieser Test verlangt, dass sie gleich sind.
"""

import inspect
import re
import zipfile
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

import pytest
from test_docs_complete import _klassen_der_bibliothek, buendel

WURZEL = Path(__file__).resolve().parent.parent
SKILL = WURZEL / ".claude" / "skills" / "edu-sharing-python"


def _abgleich() -> ModuleType:
    """``scripts/sync_skill.py``, ohne es auszufuehren.

    Die Wache haengt an derselben Abbildung, die das Skript benutzt -- eine
    zweite Liste hier waere eine, die auseinanderlaeuft.
    """
    spec = spec_from_file_location("sync_skill", WURZEL / "scripts" / "sync_skill.py")
    assert spec is not None and spec.loader is not None
    modul = module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_die_nachschlagedateien_sind_kopien_der_doku():
    """Zeichen fuer Zeichen -- sonst liest das Modell eine veraltete Referenz."""
    abweichend = _abgleich().differences(WURZEL)
    assert not abweichend, (
        "Der Skill-Ordner weicht von docs/ ab -- `python scripts/sync_skill.py` "
        "behebt es:\n  " + "\n  ".join(abweichend))


def test_die_abbildung_nimmt_mit_was_der_plan_verlangt():
    """Die Abbildung selbst gegen die Anforderung: beide Sprachen von REFERENCE
    und FLOWS, und jedes Beispiel. Fehlte eine Datei in der Abbildung, waeren
    Skript und Wache sich einig -- und beide falsch."""
    quellen = {q.relative_to(WURZEL).as_posix() for q, _ in _abgleich().pairs(WURZEL)}
    verlangt = {"docs/REFERENCE.md", "docs/REFERENCE.de.md",
                "docs/FLOWS.md", "docs/FLOWS.de.md"}
    verlangt |= {p.relative_to(WURZEL).as_posix()
                 for p in (WURZEL / "docs" / "examples").glob("*.py")}
    assert verlangt <= quellen, f"nicht in der Abbildung: {sorted(verlangt - quellen)}"


def test_die_kopien_behalten_ihre_namen():
    """``FLOWS.md`` verweist auf ``examples/05_flow_search.py``. Das bleibt nur
    gueltig, wenn die Kopie unter demselben relativen Namen liegt."""
    for quelle, kopie in _abgleich().pairs(WURZEL):
        von_docs = quelle.relative_to(WURZEL / "docs").as_posix()
        im_skill = kopie.relative_to(
            WURZEL / ".claude" / "skills" / "edu-sharing-python" / "reference").as_posix()
        assert von_docs == im_skill


def test_der_abgleich_sieht_jede_abweichung(tmp_path):
    """Gegenprobe: fehlend, veraltet und verwaist fallen auf -- und das
    Skript behebt alle drei."""
    abgleich = _abgleich()
    for name in ("REFERENCE.md", "REFERENCE.de.md", "FLOWS.md", "FLOWS.de.md"):
        (tmp_path / "docs" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / name).write_text(f"# {name}\n", encoding="utf-8")
    (tmp_path / "docs" / "examples").mkdir()
    (tmp_path / "docs" / "examples" / "01_a.py").write_text("print(1)\n", encoding="utf-8")

    assert "missing: .claude/skills/edu-sharing-python/reference/FLOWS.md" in (
        abgleich.differences(tmp_path))
    abgleich.synchronise(tmp_path)
    assert abgleich.differences(tmp_path) == []

    ziel = tmp_path / ".claude" / "skills" / "edu-sharing-python" / "reference"
    (ziel / "FLOWS.md").write_text("# von Hand geaendert\n", encoding="utf-8")
    (ziel / "examples" / "99_alt.py").write_text("print(99)\n", encoding="utf-8")
    assert abgleich.differences(tmp_path) == [
        "stale: .claude/skills/edu-sharing-python/reference/FLOWS.md",
        "orphaned: .claude/skills/edu-sharing-python/reference/examples/99_alt.py",
    ]
    abgleich.synchronise(tmp_path)
    assert abgleich.differences(tmp_path) == []
    assert not (ziel / "examples" / "99_alt.py").exists()


def test_der_abgleich_vergleicht_wie_git(tmp_path):
    """CRLF gegen LF ist kein Unterschied -- fuer Git nicht, also auch hier nicht.

    ``.gitattributes`` legt ``eol=lf`` fest, aber ein Arbeitsbaum, der vor
    dieser Regel ausgecheckt wurde, behaelt CRLF (gemessen am 11.09.2026: 1172
    Dateien auf dem Rechner, auf dem der Skill entstand). Schreibt Git nach
    einem Pull nur die Quelle neu, stuende die Kopie byte-verschieden da,
    obwohl Git beide fuer gleich haelt -- ein roter Test ohne Befund.
    """
    abgleich = _abgleich()
    for name in ("REFERENCE.md", "REFERENCE.de.md", "FLOWS.md", "FLOWS.de.md"):
        (tmp_path / "docs" / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / name).write_bytes(b"# Titel\r\nText\r\n")
    (tmp_path / "docs" / "examples").mkdir()
    abgleich.synchronise(tmp_path)
    kopie = tmp_path / ".claude" / "skills" / "edu-sharing-python" / "reference" / "FLOWS.md"
    assert kopie.read_bytes() == b"# Titel\nText\n", "die Kopie folgt eol=lf"
    assert abgleich.differences(tmp_path) == []
    kopie.write_bytes(b"# Titel\nAnderer Text\n")
    assert abgleich.differences(tmp_path) == [
        "stale: .claude/skills/edu-sharing-python/reference/FLOWS.md"]


# --- Die Vermittlungswache (Plan T3b) ---------------------------------------
#
# ``test_docs_complete`` fragt, ob jeder oeffentliche Name **vorkommt**.
# Gemessen am 11.09.2026 kam jeder vor -- und doch zeigte SKILL.md fuer 59 von
# 83 Aufrufformen mit Pflichtparametern nicht, was hineingehoert:
# ``set_property`` stand da, ``set_property(prop, value)`` nicht. Ein Modell,
# das nur den Namen kennt, raet die Argumente.
#
# Gezaehlt wird je Klasse, nicht je Name: ``delete`` gibt es an ``Comments``,
# ``Relations`` und ``Node`` mit drei verschiedenen Pflichtparametern. Die
# Huellen in ``_sync`` bleiben aussen vor -- sie spiegeln die asynchrone
# Oberflaeche Name fuer Name, wie ``test_docs_complete`` es festhaelt.

EINSTIEGE = ("SKILL.md", "SKILL.de.md")


def _pflichtparameter(klasse: type, name: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """``(positionale, nur benannte)`` Parameter ohne Vorgabe -- ohne ``self``
    und ``cls``, ohne ``*args`` und ``**kwargs``. ``None`` fuer Properties und
    alles ohne Python-Rumpf."""
    roh = vars(klasse)[name]
    funktion = roh.__func__ if isinstance(roh, (classmethod, staticmethod)) else roh
    if not inspect.isfunction(funktion):
        return None
    parameter = list(inspect.signature(funktion).parameters.values())
    if not isinstance(roh, staticmethod):
        parameter = parameter[1:]
    ohne_vorgabe = [p for p in parameter if p.default is p.empty]
    return (tuple(p.name for p in ohne_vorgabe
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)),
            tuple(p.name for p in ohne_vorgabe if p.kind is p.KEYWORD_ONLY))


def _aufrufformen() -> dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]]:
    """Jede Form ``(name, positionale, nur benannte)`` -> die Methoden, die sie haben.

    ``from_response(data)`` haben zehn Klassen; eine Zeile, die die Form
    zeigt, zeigt sie fuer alle.
    """
    formen: dict[tuple[str, tuple[str, ...], tuple[str, ...]], list[str]] = {}
    for klassenname, klasse in sorted(_klassen_der_bibliothek().items()):
        if klasse.__module__ == "edusharing._sync":
            continue
        for name in vars(klasse):
            if name.startswith("_"):
                continue
            pflicht = _pflichtparameter(klasse, name)
            if pflicht is not None:
                formen.setdefault((name, *pflicht), []).append(f"{klassenname}.{name}")
    return formen


def _argumente(text: str, start: int) -> list[str] | None:
    """Die Argumente ab ``start`` bis zur passenden Klammer, an den Kommas der
    obersten Ebene getrennt -- ``None``, wenn die Klammer nicht schliesst."""
    tiefe, teile, aktuell, zeichen_in = 0, [], [], ""
    for ch in text[start:start + 500]:
        if zeichen_in:
            aktuell.append(ch)
            zeichen_in = "" if ch == zeichen_in else zeichen_in
            continue
        if ch in "\"'":
            zeichen_in = ch
        elif ch in "([{":
            tiefe += 1
        elif ch in ")]}":
            if tiefe == 0:
                teile.append("".join(aktuell).strip())
                return [t for t in teile if t]
            tiefe -= 1
        elif ch == "," and tiefe == 0:
            teile.append("".join(aktuell).strip())
            aktuell = []
            continue
        aktuell.append(ch)
    return None


def _zeigt(text: str, name: str, positional: tuple[str, ...], benannt: tuple[str, ...]) -> bool:
    """Steht ``name(`` mit genau diesen Parameternamen da? Die positionalen in
    ihrer Reihenfolge vorn (``prop``, ``prop=…`` oder ``prop: str``), die nur
    benannten als ``k=…`` irgendwo in der Liste."""
    for treffer in re.finditer(rf"(?<![A-Za-z0-9_]){name}\(", text):
        teile = _argumente(text, treffer.end())
        if teile is None or len(teile) < len(positional):
            continue
        if not all(re.match(rf"{p}\b(?!\()", teile[i]) for i, p in enumerate(positional)):
            continue
        if all(any(re.match(rf"{k}\s*[=:]", t) for t in teile) for k in benannt):
            return True
    return False


@pytest.mark.parametrize("datei", EINSTIEGE)
def test_der_einstieg_zeigt_jede_aufrufform_mit_ihren_pflichtparametern(datei: str):
    """Der Einstieg selbst, nicht die Referenz: das Modell liest ihn zuerst,
    und jede Datei, die es dafuer oeffnen muss, ist ein Schritt, den es
    auslassen kann."""
    text = (SKILL / datei).read_text(encoding="utf-8")
    fehlend = [f"{name}({', '.join([*positional, *(k + '=' for k in benannt)])})"
               f"  [{', '.join(methoden)}]"
               for (name, positional, benannt), methoden in sorted(_aufrufformen().items())
               if (positional or benannt) and not _zeigt(text, name, positional, benannt)]
    assert not fehlend, (f"{datei} zeigt {len(fehlend)} Aufrufformen nicht mit ihren "
                         "Pflichtparametern:\n  " + "\n  ".join(fehlend))


def test_die_vermittlungswache_sieht_falsche_und_fehlende_namen():
    """Gegenprobe: nur der Aufruf mit den echten Namen zaehlt."""
    assert _zeigt("| `node.set_property(prop, value, *, verify=True)` | `Node` |",
                  "set_property", ("prop", "value"), ())
    assert not _zeigt("`node.set_property(value)`", "set_property", ("prop", "value"), ())
    assert not _zeigt('`node.set_property("cclom:title", "x")`',
                      "set_property", ("prop", "value"), ())
    assert not _zeigt("`node.reset_property(prop, value)`", "set_property", ("prop", "value"), ())
    assert _zeigt("`templates.chat(configs, *, context_node_id=…)`",
                  "chat", ("configs",), ("context_node_id",))
    assert not _zeigt("`templates.chat(configs)`", "chat", ("configs",), ("context_node_id",))


def test_die_aufrufformen_sind_die_gemessenen():
    """Woran die Wache haengt: je Klasse gezaehlt, die Huellen der blockierenden
    Fassade aussen vor. Die Form von ``set_property`` und die drei von
    ``delete`` muessen darunter sein -- sonst zaehlt die Wache etwas anderes
    als gemessen."""
    formen = _aufrufformen()
    assert ("set_property", ("prop", "value"), ()) in formen
    assert ("delete", ("comment_id",), ()) in formen
    assert ("delete", ("from_node", "relation_type", "to_node"), ()) in formen
    assert ("delete", (), ()) in formen
    assert not any(m.startswith("Sync") for ms in formen.values() for m in ms)


def _zeigt_ergebnis(text: str, name: str) -> bool:
    """``name(`` in einer Tabellenzeile mit einer zweiten Spalte -- die sagt,
    was zurueckkommt -- oder in einem Python-Beispiel."""
    aufruf = re.compile(rf"(?<![A-Za-z0-9_]){name}\(")
    for zeile in text.splitlines():
        if zeile.startswith("|") and aufruf.search(zeile):
            zellen = [z.strip() for z in zeile.strip().strip("|").split("|")]
            if sum(bool(z) for z in zellen) >= 2:
                return True
    return any(aufruf.search(block)
               for block in re.findall(r"```(?:python|py)\n(.*?)```", text, re.S))


def test_die_ergebniswache_sieht_eine_zeile_ohne_ergebnis():
    """Gegenprobe: der Name allein, oder eine Zeile ohne zweite Spalte, zaehlt nicht."""
    assert _zeigt_ergebnis("| `repo.whoami()` | `Identity` |", "whoami")
    assert _zeigt_ergebnis("```python\nme = await repo.whoami()\n```", "whoami")
    assert not _zeigt_ergebnis("| `repo.whoami()` | |", "whoami")
    assert not _zeigt_ergebnis("Mit `repo.whoami()` fragt man nach sich selbst.", "whoami")
    # Gemessen am 11.09.2026: 35 Formen -- 58 Methoden, von denen viele sich
    # eine teilen (``list()``, ``get()``, ``aclose()``).
    ohne = [f for f in _aufrufformen() if not f[1] and not f[2]]
    assert len(ohne) > 30, f"nur {len(ohne)} Formen ohne Pflichtparameter -- zaehlt die Wache?"


@pytest.mark.parametrize("datei", EINSTIEGE)
def test_jeder_aufruf_ohne_pflichtparameter_zeigt_was_zurueckkommt(datei: str):
    """``whoami()`` braucht nichts -- aber wer es ruft, muss wissen, was
    zurueckkommt. Im Buendel, nicht zwingend im Einstieg: dort steht die
    Tabelle, hier genuegt die Referenz."""
    text = buendel(datei)
    fehlend = [f"{name}()  [{', '.join(methoden)}]"
               for (name, positional, benannt), methoden in sorted(_aufrufformen().items())
               if not positional and not benannt and not _zeigt_ergebnis(text, name)]
    assert not fehlend, (f"Buendel zu {datei} zeigt fuer {len(fehlend)} Aufrufe nicht, was "
                         "zurueckkommt:\n  " + "\n  ".join(fehlend))


# --- Die Regeln der Anbieter (Plan T7) --------------------------------------
#
# Abgerufen am 11.09.2026: Anthropic empfiehlt fuer SKILL.md unter 500 Zeilen
# und Nachschlagedateien, die der Einstieg direkt verlinkt -- eine Ebene tief,
# denn ein Modell liest eine Datei, auf die eine andere nur verweist, oft nur
# an. Die Frontmatter: name hoechstens 64 Zeichen aus a-z, 0-9 und "-", ohne
# "anthropic" und "claude"; description hoechstens 1024 Zeichen, keine
# XML-Tags (platform.claude.com, Agent Skills).

_VERWEIS = re.compile(r"]\(([^)#][^)]*)\)")


def _verweise(datei: Path) -> list[Path]:
    """Jedes relative Verweisziel einer Datei, aufgeloest, ohne Anker."""
    return [(datei.parent / ziel.split("#")[0]).resolve()
            for ziel in _VERWEIS.findall(datei.read_text(encoding="utf-8"))
            if not ziel.startswith(("http://", "https://", "mailto:"))]


@pytest.mark.parametrize("datei", EINSTIEGE)
def test_der_einstieg_bleibt_unter_500_zeilen(datei: str):
    zeilen = len((SKILL / datei).read_text(encoding="utf-8").splitlines())
    assert zeilen < 500, f"{datei}: {zeilen} Zeilen -- Einzelheiten gehoeren nach reference/"


@pytest.mark.parametrize("datei", EINSTIEGE)
def test_kein_verweis_des_einstiegs_fuehrt_aus_dem_skill_ordner(datei: str):
    """Ausserhalb des Repositoriums gibt es ``../../../docs`` nicht."""
    draussen = [str(z) for z in _verweise(SKILL / datei)
                if not z.is_relative_to(SKILL.resolve()) or not z.exists()]
    assert not draussen, f"{datei} verweist aus dem Skill-Ordner oder ins Leere:\n  " + (
        "\n  ".join(draussen))


@pytest.mark.parametrize("datei", EINSTIEGE)
def test_der_einstieg_verlinkt_jede_nachschlagedatei_direkt(datei: str):
    """Eine Ebene tief: jede Nachschlagedatei seiner Sprache und jedes Beispiel."""
    deutsch = datei.endswith(".de.md")
    verlangt = {p.resolve() for p in (SKILL / "reference").glob("*.md")
                if p.name.endswith(".de.md") == deutsch}
    verlangt |= {p.resolve() for p in (SKILL / "reference" / "examples").glob("*.py")}
    fehlend = sorted(p.relative_to(SKILL.resolve()).as_posix()
                     for p in verlangt - set(_verweise(SKILL / datei)))
    assert not fehlend, f"{datei} verlinkt nicht direkt: {fehlend}"


def test_keine_nachschlagedatei_verweist_aus_dem_skill_ordner():
    """Auch die Kopien und die Fallen: sie verweisen untereinander und auf die
    Beispiele, gemessen -- und so soll es bleiben."""
    draussen = [f"{d.name} -> {z}" for d in sorted((SKILL / "reference").glob("*.md"))
                for z in _verweise(d)
                if not z.is_relative_to(SKILL.resolve()) or not z.exists()]
    assert not draussen, "\n  ".join(draussen)


def _frontmatter(text: str) -> dict[str, str]:
    """Die einzeiligen Felder zwischen den beiden ``---`` am Anfang."""
    treffer = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert treffer, "keine Frontmatter am Anfang"
    return dict(re.findall(r"^([a-z_-]+):\s*(.+)$", treffer.group(1), re.M))


def test_die_frontmatter_folgt_den_regeln_der_anbieter():
    felder = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
    name, beschreibung = felder.get("name", ""), felder.get("description", "")
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name), name
    assert "anthropic" not in name and "claude" not in name, name
    assert 0 < len(beschreibung) <= 1024, f"{len(beschreibung)} Zeichen"
    assert not re.search(r"<[A-Za-z/][^>]*>", beschreibung), "XML-Tag in der description"
    assert name == SKILL.name, "der Name ist der Ordnername -- so erwarten es alle drei Ziele"


def test_der_deutsche_einstieg_ist_eine_begleitdatei():
    """Ohne Frontmatter: sonst gaebe es zwei Skills mit fast denselben Ausloesern."""
    assert not (SKILL / "SKILL.de.md").read_text(encoding="utf-8").startswith("---")


def test_die_frontmatterwache_sieht_einen_verstoss():
    """Gegenprobe fuer den Leser der Frontmatter selbst."""
    felder = _frontmatter("---\nname: Mein Skill\ndescription: <b>x</b>\n---\n# T\n")
    assert felder == {"name": "Mein Skill", "description": "<b>x</b>"}
    assert not re.fullmatch(r"[a-z0-9-]{1,64}", felder["name"])


# --- Die ZIP fuer claude.ai (Plan T8) ---------------------------------------
#
# claude.ai nimmt einen Skill als ZIP hoch: der Skill-Ordner als Wurzel, eine
# description von hoechstens 200 Zeichen (Hilfe-Artikel 12512198, abgerufen am
# 11.09.2026). Claude Code erlaubt 1536, die Plattform 1024 -- der Einstieg im
# Repositorium behaelt die lange Fassung mit ihren Ausloesern, die ZIP traegt
# deren ersten Satz.


def _zipbau() -> ModuleType:
    spec = spec_from_file_location("build_skill_zip", WURZEL / "scripts" / "build_skill_zip.py")
    assert spec is not None and spec.loader is not None
    modul = module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_die_zip_hat_den_skill_ordner_als_wurzel_und_alles_darin(tmp_path):
    ziel = _zipbau().build(tmp_path / "skill.zip")
    with zipfile.ZipFile(ziel) as z:
        namen = set(z.namelist())
    erwartet = {f"edu-sharing-python/{p.relative_to(SKILL).as_posix()}"
                for p in SKILL.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert "edu-sharing-python/SKILL.md" in namen
    assert "edu-sharing-python/reference/REFERENCE.md" in namen
    assert namen == erwartet, f"missing: {erwartet - namen}, zu viel: {namen - erwartet}"


def test_die_zip_traegt_eine_beschreibung_die_claude_ai_nimmt(tmp_path):
    with zipfile.ZipFile(_zipbau().build(tmp_path / "skill.zip")) as z:
        eingepackt = z.read("edu-sharing-python/SKILL.md").decode("utf-8")
    felder = _frontmatter(eingepackt)
    assert felder["name"] == "edu-sharing-python"
    assert 0 < len(felder["description"]) <= 200, len(felder["description"])
    lang = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))["description"]
    assert lang.startswith(felder["description"]), "der erste Satz der langen Fassung"
    rumpf = (SKILL / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert eingepackt.split("\n---\n", 1)[1] == rumpf.split("\n---\n", 1)[1], (
        "hinter der Frontmatter aendert die ZIP nichts")


def test_die_kurzbeschreibung_verweigert_einen_zu_langen_ersten_satz():
    """Lieber ein Fehler beim Bauen als eine abgeschnittene Beschreibung."""
    zipbau = _zipbau()
    assert zipbau.short_description("Kurz genug. Und mehr.") == "Kurz genug."
    with pytest.raises(ValueError, match="200"):
        zipbau.short_description("x" * 201 + ". Rest.")


def test_die_zip_ist_reproduzierbar(tmp_path):
    """Zwei Laeufe, dieselben Bytes -- sonst sieht jede ZIP neu aus."""
    zipbau = _zipbau()
    assert zipbau.build(tmp_path / "a.zip").read_bytes() == zipbau.build(
        tmp_path / "b.zip").read_bytes()
