"""Was ein Skill-Dokument ueber sich sagt -- ohne I/O.

Die Redaktion schreibt Verweise als Bloecke in die Markdown-Datei und gliedert
eine Registry mit Ueberschriften. Das ist schon ein Manifest, es steht nur in
Prosa. Es HIER zu lesen statt einem Modell zu ueberlassen ist der Punkt: eine
Knoten-ID in einer URL in einem Markdown-Link in einem Block ist eine
Extraktionsaufgabe, und die hat eine Fehlerquote. Regeln wie im MCP
(``skill-references.ts``, ``markdown-sections.ts``, ``registry-contexts.ts``),
gegen Staging gemessen: ``skill_registry.md`` traegt 7 ``::: ki-skill``-Bloecke
und 3 Kontexte.
"""

import pytest

from edusharing.skills_markdown import layout_contexts, parse_blocks, parse_sections

RENDER = "https://repo.test/edu-sharing/components/render/"
A = "12c04f9c-20b5-4461-804f-9c7b1a2d3e4f"
B = "ccdcae49-d4db-4e4a-9cae-49d4db1e4a11"
C = "aa11bb22-cc33-4d44-8e55-f66778899aab"
M = "0f0f0f0f-1111-4222-8333-444455556666"

REGISTRY = f"""# Skills für die Sammlung Optik

Für die Arbeit mit dieser Sammlung freigegeben. Bitte immer erst den Bestand
sichten, bevor etwas Neues entsteht.

::: ki-skill
[Lehrprofil auswerten]({RENDER}{A})
:::

## Unterricht vorbereiten

Für die Sekundarstufe I zuerst den Fragen-Skill.

::: wlo-material
![Titel](https://repo.test/edu-sharing/preview?nodeId={M})
[**Ein Arbeitsblatt**](https://example.org/quelle) — Lizenz: CC BY
:::

::: ki-skill
[**Fragen generieren**]({RENDER}{B})
:::

### Wochenplanung

Nur für ganze Unterrichtsreihen.

::: ki-skill
[Skill\\_Reihenplan\\_entwerfen]({RENDER}{C})
:::

## Material erschließen

Beim Beschreiben die Fachsystematik der Sammlung verwenden.

##

Ohne Titel: gehört zum allgemeinen Teil.
"""


# --- Bloecke ---------------------------------------------------------------

def test_bloecke_mit_art_titel_url_und_knoten_id():
    refs = parse_blocks(REGISTRY)
    assert [(r.kind, r.node_id) for r in refs] == [
        ("ki-skill", A), ("wlo-material", M), ("ki-skill", B), ("ki-skill", C)]
    assert refs[0].title == "Lehrprofil auswerten"
    assert refs[0].url == f"{RENDER}{A}"


def test_der_titel_ist_der_erste_link_der_kein_bild_ist():
    """Beim Material zeigt der Titellink auf die QUELLE; die Knoten-ID kommt aus
    dem Vorschaubild -- das erste Vorkommen im Block gewinnt."""
    material = parse_blocks(REGISTRY)[1]
    assert material.title == "Ein Arbeitsblatt"
    assert material.url == "https://example.org/quelle"
    assert material.node_id == M


def test_hervorhebung_und_backslash_escapes_verschwinden_aus_dem_titel():
    """Gemessen an der echten Optik-Registry: ``Skill\\_X`` -- der Unterstrich
    ist escaped, weil ``_so_`` kursiv waere -- und der Backslash kam mit."""
    refs = parse_blocks(REGISTRY)
    assert refs[2].title == "Fragen generieren"
    assert refs[3].title == "Skill_Reihenplan_entwerfen"


def test_ein_block_ohne_link_verweist_auf_nichts():
    assert parse_blocks("::: ki-skill\nnur Prosa\n:::\n") == []


def test_ein_offener_block_erfindet_nichts():
    assert parse_blocks("::: ki-skill\n[X](" + RENDER + A + ")\n") == []


def test_ein_block_ohne_repositoriumsadresse_hat_keine_id():
    refs = parse_blocks("::: ki-skill\n[Extern](https://example.org/x)\n:::\n")
    assert refs[0].title == "Extern" and refs[0].node_id == ""


def test_offsets_zeigen_auf_den_oeffnenden_zaun():
    refs = parse_blocks(REGISTRY)
    for r in refs:
        assert REGISTRY.startswith(":::", r.offset)


def test_nur_die_genannten_arten():
    assert [r.kind for r in parse_blocks(REGISTRY, kinds=("ki-skill",))] == ["ki-skill"] * 3


def test_skill_id_kommt_aus_dem_titellink_auch_mit_fremdem_vorschaubild():
    text = f"::: ki-skill\n![Symbol]({RENDER}{B})\n[Skill]({RENDER}{A})\n:::\n"
    assert parse_blocks(text)[0].node_id == A


def test_custom_skill_id_kommt_ebenfalls_aus_dem_titellink():
    text = f"::: ai-skill\n![Symbol]({RENDER}{B})\n[Skill]({RENDER}{A})\n:::\n"
    refs = parse_blocks(text, ("ai-skill",), skill_kind="ai-skill")
    assert refs[0].node_id == A


def test_unclosed_link_in_a_closed_block_takes_bounded_time():
    import time

    text = "::: ki-skill\n" + "[" * 64_000 + "\n:::\n"
    start = time.perf_counter()
    assert parse_blocks(text) == []
    assert time.perf_counter() - start < 3.0


def test_large_outline_caps_work_but_preserves_paths_and_total():
    import time

    text = "".join(f"## Context {i}\nInstruction.\n" for i in range(16_000))
    text += f"::: ki-skill\n[Last]({RENDER}{A})\n:::\n"
    start = time.perf_counter()
    layout = layout_contexts(text, parse_blocks(text))
    assert time.perf_counter() - start < 3.0
    assert len(layout.contexts) == 50
    assert layout.truncated == (50, 16_000)
    assert layout.paths == ["Context 15999"]
    assert layout.contexts[0].instruction == "Instruction."


# --- Abschnitte ------------------------------------------------------------

def test_abschnitte_mit_ebene_titel_und_reichweite():
    secs = parse_sections(REGISTRY)
    assert [(s.level, s.title) for s in secs] == [
        (1, "Skills für die Sammlung Optik"), (2, "Unterricht vorbereiten"),
        (3, "Wochenplanung"), (2, "Material erschließen"), (2, "")]
    h2 = secs[1]
    assert REGISTRY[h2.heading_start:].startswith("## Unterricht")
    assert h2.end == secs[3].heading_start, "eine H2 schliesst erst die naechste H2"
    assert secs[2].end == secs[3].heading_start, "eine H3 endet auch an der naechsten H2"


def test_setext_und_zaeune_sind_keine_ueberschriften():
    text = "Titel\n=====\n\n```\n# kein Titel\n```\n\n#nicht\n\n## Echt\n"
    assert [s.title for s in parse_sections(text)] == ["Echt"]


@pytest.mark.parametrize(("zeile", "erwartet"), [
    ("# Titel", [(1, "Titel")]),
    ("## Titel  ", [(2, "Titel")]),
    ("###\tTab", [(3, "Tab")]),
    ("#", [(1, "")]),
    ("#   ", [(1, "")]),
    ("# C#", [(1, "C#")]),
    ("## Titel ##", [(2, "Titel")]),
    ("#kein", []),
    ("    # eingerueckt", []),
    ("   # drei", [(1, "drei")]),
    ("####### sieben", []),
    ("# a  b  ", [(1, "a  b")]),
])
def test_ueberschriften_an_ihren_raendern(zeile, erwartet):
    """Gepinnt vor dem Umbau des Musters (Audit SEC-23-1): was eine Ueberschrift
    ist und welcher Titel herauskommt, darf sich dabei nicht aendern -- nur,
    wie lange die Antwort dauert."""
    assert [(s.level, s.title) for s in parse_sections(zeile + "\n")] == erwartet


def test_eine_ueberschrift_mit_langem_leerraum_bleibt_linear():
    """Audit SEC-23-1 (23.09.2026): das Muster las den Leerraum hinter dem Titel
    an jeder Stelle eines Laufs neu -- quadratisch in seiner Laenge. Gemessen:
    16 000 Leerzeichen zwischen zwei Zeichen einer Ueberschrift 1,4 s, eine
    1-MiB-Zeile hochgerechnet anderthalb Stunden blockierte Ereignisschleife.
    Eine Registry kommt aus dem Repositorium, also von anderen."""
    import time
    titel = "x" + " " * 60_000 + "y"
    start = time.perf_counter()
    abschnitte = parse_sections(f"# {titel}\n")
    assert time.perf_counter() - start < 3.0
    assert [(s.level, s.title) for s in abschnitte] == [(1, titel)]


# --- Kontexte --------------------------------------------------------------

def test_ein_zweiter_oeffner_im_offenen_block_ist_text():
    """Gepinnt vor dem Umbau (Audit SEC-2): ein ``::: kind`` innerhalb eines
    offenen Blocks ist Fliesstext bis zum naechsten blanken ``:::`` -- so las
    es der Regex, so muss es der Zeilenautomat lesen."""
    text = "::: ki-skill\n[A](https://a.test)\n::: ki-skill\n[B](https://b.test)\n:::\n"
    refs = parse_blocks(text)
    assert [(r.title, r.url, r.offset) for r in refs] == [("A", "https://a.test", 0)]


def test_die_parser_bleiben_bei_vielen_zaeunen_und_offenen_bloecken_linear():
    """Audit SEC-2 (06.09.2026): der nicht-gierige Block-Regex lief von jedem
    Oeffner ohne Schliesser bis zum Dokumentende, und die Abschnittssuche
    fragte fuer jede Zeile jeden Zaun. 10 000 Bloecke mit je einem Zaun
    brauchten Minuten; ein Registry-Dokument kommt aus dem Repositorium,
    also von anderen."""
    import time
    text = "".join(
        f"::: ki-skill\n```\ncode {i}\n```\n# Titel {i}\n" for i in range(10_000)
    )
    start = time.perf_counter()
    assert parse_blocks(text) == []
    assert len(parse_sections(text)) == 10_000
    assert time.perf_counter() - start < 3.0


def test_kontexte_aus_benannten_h2_und_h3():
    refs = parse_blocks(REGISTRY)
    layout = layout_contexts(REGISTRY, refs)
    assert [c.path for c in layout.contexts] == [
        "Unterricht vorbereiten", "Unterricht vorbereiten/Wochenplanung",
        "Material erschließen"]
    assert layout.contexts[0].skills == [B]
    assert layout.contexts[1].skills == [C]
    assert layout.contexts[2].skills == []
    assert layout.paths == [None, "Unterricht vorbereiten", "Unterricht vorbereiten",
                            "Unterricht vorbereiten/Wochenplanung"]


def test_allgemeiner_teil_sammelt_was_ausserhalb_liegt():
    layout = layout_contexts(REGISTRY, parse_blocks(REGISTRY))
    assert layout.general.skills == [A]
    assert "Bestand" in layout.general.instruction
    assert "Ohne Titel" in layout.general.instruction, "eine namenlose H2 ist transparent"


def test_die_anweisung_endet_am_ersten_block():
    layout = layout_contexts(REGISTRY, parse_blocks(REGISTRY))
    erste = layout.contexts[0].instruction
    assert "Fragen-Skill" in erste
    assert ":::" not in erste and "preview?nodeId" not in erste, \
        "ein Materialblock beendet die Anweisung ebenso"


def test_eine_h2_umfasst_ihre_h3():
    layout = layout_contexts(REGISTRY, parse_blocks(REGISTRY))
    eltern, kind = layout.contexts[0], layout.contexts[1]
    assert eltern.range[0] < kind.range[0] and kind.range[1] <= eltern.range[1]


def test_mehr_als_fuenfzig_kontexte_werden_gemeldet():
    text = "".join(f"## K{i}\n\n::: ki-skill\n[S]({RENDER}{A})\n:::\n\n" for i in range(55))
    layout = layout_contexts(text, parse_blocks(text))
    assert len(layout.contexts) == 50
    assert layout.truncated == (50, 55)


# --- Zaeune und Prosa (Review 02.09.2026) ------------------------------------

def test_ein_beispiel_im_codezaun_ist_kein_verweis():
    """Ein SKILL.md, das die Blocksyntax ZEIGT, verweist auf nichts -- sonst
    erfaende der Parser einen Verweis, was er nie darf."""
    beispiel = f"::: ki-skill\n[Beispiel]({RENDER}{A})\n:::\n"
    gezeigt = (f"So sieht ein Block aus:\n\n```\n{beispiel}```\n\n"
               f"::: ki-skill\n[Echt]({RENDER}{B})\n:::\n")
    assert [r.node_id for r in parse_blocks(gezeigt)] == [B]


def test_ohne_blockarten_kein_block():
    assert parse_blocks(REGISTRY, kinds=()) == []


def test_prosa_eines_unbenannten_unterabschnitts_gehoert_dem_besitzer():
    """Ein unbenanntes ### ist durchsichtig -- fuer seine Skills UND seine Prosa."""
    doc = f"## Vorbereiten\n\nA.\n\n###\n\nB.\n\n::: ki-skill\n[X]({RENDER}{A})\n:::\n"
    layout = layout_contexts(doc, parse_blocks(doc))
    assert layout.contexts[0].instruction == "A.\n\nB."
    assert layout.contexts[0].skills == [A]


def test_eine_h4_schneidet_die_prosa_nicht():
    """Nur ##/### eroeffnen Kontexte; eine tiefere Ueberschrift ist Teil der Prosa."""
    doc = "## Vorbereiten\n\nA.\n\n#### Hinweis\n\nB.\n"
    layout = layout_contexts(doc, [])
    assert layout.contexts[0].instruction == "A.\n\n#### Hinweis\n\nB."


def test_ein_unvollstaendiges_beispiel_im_zaun_verschluckt_keinen_echten_block():
    """Ein Zaun, der nur den oeffnenden Block zeigt: bisher lief der Treffer vom
    Zaun bis zum schliessenden ::: des naechsten ECHTEN Blocks -- und der war weg."""
    doc = (f"```\n::: ki-skill\n[Beispiel]({RENDER}{A})\n```\n\n"
           f"::: ki-skill\n[Echt]({RENDER}{B})\n:::\n")
    assert [r.node_id for r in parse_blocks(doc)] == [B]


# --- F12 (Fremdpruefung 09.09.2026): Fences und Ueberschriften -------------
#
# Zwei getrennte Ursachen in einer Datei.
#
# **Die Fence-Laenge wurde nicht behalten.** ``^ {0,3}(```|~~~)`` liefert immer
# drei Zeichen, egal wie lang der Fence wirklich ist. Ein Vierfach-Fence --
# die uebliche Art, einen Codeblock *in* einem Codeblock zu zeigen -- wurde
# damit vom ersten inneren Dreifach-Fence geschlossen, und der Rest des
# Beispiels zerfiel in Stuecke. Gemessen am 09.09.2026 galt ein
# ``::: ki-skill``-Beispiel innerhalb eines Codeblocks als **aktiver
# Verweis**: Dokumentation wandert damit in den Skill-Katalog.
#
# **``.rstrip("#")`` nahm die Raute des Titels.** ``## C#`` ergab ``C``. Nach
# den Markdown-Regeln schliesst eine Rautenfolge eine Ueberschrift nur, wenn
# ein Leerzeichen davorsteht.

VIERFACH = (
    "# Anleitung\n"
    "\n"
    "````markdown\n"
    "```\n"
    "::: ki-skill\n"
    "[Beispiel](https://repo.test/edu-sharing/components/render/"
    "11111111-1111-1111-1111-111111111111)\n"
    ":::\n"
    "```\n"
    "````\n"
)


def test_ein_vierfach_fence_bleibt_ein_block():
    """Die Ursache, direkt gemessen: ein Renderer sieht hier einen Block."""
    from edusharing.skills_markdown import _fenced_spans

    anfang = VIERFACH.index("````markdown")
    assert _fenced_spans(VIERFACH) == [(anfang, len(VIERFACH))]


def test_ein_beispiel_im_codeblock_ist_kein_verweis():
    """Und die Wirkung, an der oeffentlichen Funktion."""
    assert parse_blocks(VIERFACH) == []


@pytest.mark.parametrize("zeichen", ["`", "~"])
@pytest.mark.parametrize("laenge", [3, 4, 5])
def test_ein_fence_wird_nur_von_einem_mindestens_so_langen_geschlossen(zeichen, laenge):
    """Die Markdown-Regel: gleiches Zeichen, mindestens dieselbe Laenge."""
    from edusharing.skills_markdown import _fenced_spans

    fence = zeichen * laenge
    kurz = zeichen * (laenge - 1) if laenge > 3 else ""
    text = f"{fence}\n{kurz}\ninnen\n{fence}\ndraussen\n"
    spans = _fenced_spans(text)
    assert len(spans) == 1
    assert text[spans[0][0]:spans[0][1]].endswith(f"{fence}\n")
    assert "draussen" not in text[spans[0][0]:spans[0][1]]


def test_ein_laengerer_fence_schliesst_einen_kuerzeren():
    """Die Gegenrichtung, damit die Regel nicht zu streng wird."""
    from edusharing.skills_markdown import _fenced_spans

    text = "```\ninnen\n`````\ndraussen\n"
    spans = _fenced_spans(text)
    assert len(spans) == 1
    assert "draussen" not in text[spans[0][0]:spans[0][1]]


def test_eine_abschlusszeile_mit_infozeichenkette_schliesst_nicht():
    """Auch eine Regel: der schliessende Fence traegt nichts hinter sich."""
    from edusharing.skills_markdown import _fenced_spans

    text = "```\ninnen\n``` python\nweiter\n"
    spans = _fenced_spans(text)
    assert spans == [(0, len(text))], "unschliessbar, also bis zum Ende"


def test_ein_anderes_zeichen_schliesst_nicht():
    from edusharing.skills_markdown import _fenced_spans

    text = "```\ninnen\n~~~\nweiter\n"
    assert _fenced_spans(text) == [(0, len(text))]


@pytest.mark.parametrize("zeile,titel", [
    ("## C#", "C#"),
    ("## F#", "F#"),
    ("# C++ und C#", "C++ und C#"),
    ("## Titel ###", "Titel"),
    ("## Titel #", "Titel"),
    ("## ###", ""),
    ("## Titel", "Titel"),
])
def test_die_raute_faellt_nur_nach_der_markdown_regel(zeile, titel):
    """Eine schliessende Rautenfolge braucht ein Leerzeichen davor. ``C#`` hat
    keins -- die Raute gehoert zum Namen."""
    abschnitte = parse_sections(zeile + "\nInhalt\n")
    assert [a.title for a in abschnitte] == [titel]
