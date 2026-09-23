# Datenmodell und Fallen — edu-sharing für Python

*[English version: TRAPS.md](TRAPS.md)*

Teil des Skills `edu-sharing-python` — sein Einstieg ist [SKILL.de.md](../SKILL.de.md).
Was die Aufrufe allein nicht verraten: wie edu-sharing Metadaten ablegt
(Teil 1), und was gemessen schiefgeht (Teil 2). Teil 1 vor dem Schreiben an
einen Knoten lesen, Teil 2, bevor man einem Ergebnis traut.

## Inhalt

- [1. Wie edu-sharing Metadaten ablegt](#1-wie-edu-sharing-metadaten-ablegt)
  - [1.1 Jeder Wert ist eine Liste](#11-jeder-wert-ist-eine-liste)
  - [1.2 Vier Namensräume, und sie bedeuten Verschiedenes](#12-vier-namensräume-und-sie-bedeuten-verschiedenes)
  - [1.3 `cm:name` ist ein Schlüssel, kein Titel](#13-cmname-ist-ein-schlüssel-kein-titel)
  - [1.4 Vokabularfelder tragen URIs, nie Labels](#14-vokabularfelder-tragen-uris-nie-labels)
  - [1.5 Der Metadatensatz entscheidet, was es gibt — stillschweigend](#15-der-metadatensatz-entscheidet-was-es-gibt--stillschweigend)
  - [1.6 Manche Listen sind gemeinsames Eigentum](#16-manche-listen-sind-gemeinsames-eigentum)
  - [1.7 Aspekte sind keine Typen](#17-aspekte-sind-keine-typen)
  - [1.8 Eigenschaften kommen leer, wenn man sie nicht anfordert](#18-eigenschaften-kommen-leer-wenn-man-sie-nicht-anfordert)
- [2. Die Fallen — worauf zu achten ist](#2-die-fallen--worauf-zu-achten-ist)
  - [2.1 HTTP 200 heißt nicht, dass etwas gespeichert wurde](#21-http-200-heißt-nicht-dass-etwas-gespeichert-wurde)
  - [2.2 `unresolved` ist keine Zierde](#22-unresolved-ist-keine-zierde)
  - [2.3 `total_is_lower_bound`, `truncated`, `complete`](#23-total_is_lower_bound-truncated-complete)
  - [2.4 Eine Sammlung ist kein Ordner, und eine Suche lässt sich nicht darauf einschränken](#24-eine-sammlung-ist-kein-ordner-und-eine-suche-lässt-sich-nicht-darauf-einschränken)
  - [2.5 Drei verschiedene Arten von Zugehörigkeit](#25-drei-verschiedene-arten-von-zugehörigkeit)
  - [2.6 Labels gegen URIs](#26-labels-gegen-uris)
  - [2.7 Blättern, Grenzen und Vorgaben, die stillschweigend kürzen](#27-blättern-grenzen-und-vorgaben-die-stillschweigend-kürzen)
  - [2.8 Ein Rahmenwort ruiniert eine Anfrage](#28-ein-rahmenwort-ruiniert-eine-anfrage)
  - [2.9 Tote Indexeinträge](#29-tote-indexeinträge)
  - [2.10 Die zwei Anbieter sind nicht austauschbar](#210-die-zwei-anbieter-sind-nicht-austauschbar)
  - [2.11 Auslastung abfragen, und wechseln statt warten](#211-auslastung-abfragen-und-wechseln-statt-warten)
  - [2.12 Am blockierenden `Repository` blockiert alles](#212-am-blockierenden-repository-blockiert-alles)
  - [2.13 Ein Sammlungs-Listing liefert Referenz-IDs](#213-ein-sammlungs-listing-liefert-referenz-ids)
  - [2.14 Ein Skill ist ein Datensatz mit Inhaltsart — und der Metadatensatz entscheidet, ob man danach filtern kann](#214-ein-skill-ist-ein-datensatz-mit-inhaltsart--und-der-metadatensatz-entscheidet-ob-man-danach-filtern-kann)
  - [2.15 Ein Datensatz ist nicht in dem Moment auffindbar, in dem er angelegt wurde](#215-ein-datensatz-ist-nicht-in-dem-moment-auffindbar-in-dem-er-angelegt-wurde)
  - [2.16 Der Template-Modus — der Prompt liegt auf dem Server](#216-der-template-modus--der-prompt-liegt-auf-dem-server)

## 1. Wie edu-sharing Metadaten ablegt

Die Aufrufe zu kennen genügt nicht, um richtigen Code gegen ein Repositorium zu
schreiben. Diese acht Eigenschaften des darunterliegenden Speichers erklären das
meiste, was sonst wie ein seltsames Verhalten der Bibliothek aussieht.

### 1.1 Jeder Wert ist eine Liste

Eine Eigenschaft ist nie ein einzelner Wert. `node.properties` ist
`dict[str, list[str]]` — ein Titel ist eine einelementige Liste, ein Fach mit
drei Werten eine dreielementige, und eine fehlende Eigenschaft ist ein
fehlender Schlüssel, keine leere Zeichenkette.

```python
node.properties["cclom:title"]      # ["Bruchrechnung erklärt"] -- eine Liste
node.get("cclom:title")             # "Bruchrechnung erklärt"   -- der erste Wert
node.get_all("ccm:taxonid")         # alle Werte, [] wenn ungesetzt
```

`get()`, wenn man einen will; `get_all()`, wenn das Feld berechtigt mehrere
tragen kann. Direkt in `properties` zu greifen und das Ergebnis wie eine
Zeichenkette zu behandeln ist der mit Abstand häufigste Fehler.

### 1.2 Vier Namensräume, und sie bedeuten Verschiedenes

| Präfix | Kommt aus | Beispiel |
|---|---|---|
| `cm:` | Alfrescos eigenem Inhaltsmodell — dem Dateisystem darunter | `cm:name`, `cm:title`, `cm:description` |
| `cclom:` | dem Metadatenstandard für Lernobjekte | `cclom:title`, `cclom:general_keyword`, `cclom:general_description` |
| `ccm:` | edu-sharings eigenen Ergänzungen | `ccm:taxonid`, `ccm:educationalcontext`, `ccm:wwwurl` |
| `virtual:` | nicht aus dem gespeicherten Modell — ein Dienst legt sie auf die Antwort | `virtual:profiling_widget_intention` |

Zwei Folgen daraus. Eine unter `ccm:` erfundene Eigenschaft existiert für den
Metadatensatz nicht (siehe 1.5). Und ein zurückgelesener `virtual:`-Wert gehört
dem Dienst, der ihn erzeugt hat — bei redaktionellen Seiten dem Seitenbaukasten
—, ist also zum Lesen da und über das zuständige Werkzeug zu ändern.

### 1.3 `cm:name` ist ein Schlüssel, kein Titel

`cm:name` ist der Name des Knotens **innerhalb seines Elternordners** — das
Gegenstück zu einem Dateinamen. Er muss unter den Geschwistern eindeutig sein,
und das Repositorium weist Zeichen zurück oder verstümmelt sie, die ein
Dateiname nicht tragen kann. Der lesbare Titel ist ein anderes Feld.

```python
name_from_title("Bruchrechnung: Übung 1/2")   # ein zulässiger cm:name
```

Schlimmer: das Titelfeld ist nicht überall dasselbe. **Material trägt
`cclom:title`, eine Sammlung trägt `cm:title`.** Wer das falsche schreibt,
hinterlässt ein scheinbar titelloses Objekt. Die Kurzform `title=` der
Bibliothek schreibt beide — ihr also den Vorzug geben, statt die Eigenschaft
selbst zu benennen.

### 1.4 Vokabularfelder tragen URIs, nie Labels

In `ccm:taxonid` steht nicht `"Biologie"`, sondern eine URI aus einem
SKOS-Vokabular. Ein Label zu filtern oder zu schreiben setzt einen Wert ein,
der auf nichts passt.

```python
await repo.vocab.resolve_all("ccm:taxonid", "Biologie")
# -> beide URIs: das Schulfach und das Hochschulfach (gemessen 11.09.2026)
```

Ein Label kann zu zwei Vokabularen gehören — gegen die Staging gemessen tragen
25 Fach-Labels denselben Namen einmal unter den Schulfächern und einmal unter
der Hochschulfächersystematik. Darum gibt `resolve_all` eine Liste zurück und
die Suche filtert auf alle; nur den ersten zu nehmen findet das halbe Material.

### 1.5 Der Metadatensatz entscheidet, was es gibt — stillschweigend

Jede Instanz trägt einen oder mehrere Metadatensätze (`repo.metadatasets()`),
die festlegen, welche Eigenschaften ein Objekt haben darf. Eine Eigenschaft,
die der Satz nicht kennt, wird **nicht** zurückgewiesen: das Repositorium
antwortet `200 OK` und speichert nichts.

Darum liest die Bibliothek Eigenschafts-Schreibvorgänge zurück und wirft bei
Abweichung `SilentDropError`. Das nicht abschalten — und eine `200` nicht als
Beleg nehmen.

### 1.6 Manche Listen sind gemeinsames Eigentum

`cclom:general_keyword` wird gemeinsam gepflegt — von Redaktionen, von Crawlern,
von anderen Anwendungen. Wer es setzt, ersetzt die Arbeit aller anderen.

```python
await node.add_keywords("Bruchrechnung")        # ergänzt
await node.update(keywords=["Bruchrechnung"])   # ersetzt -- selten gewollt
```

Dieselbe Vorsicht gilt für jedes listenwertige Feld, das man nicht allein
verfasst hat.

### 1.7 Aspekte sind keine Typen

Ein Knoten hat einen Typ (`ccm:io` für Material, `ccm:map` für eine Sammlung)
und beliebig viele darübergelegte Aspekte. Ein Kindobjekt ist kein eigener
Knotentyp — es ist ein gewöhnlicher Knoten mit dem Aspekt
`ccm:io_childobject`. Wer danach als Typ sucht, findet nichts.

### 1.8 Eigenschaften kommen leer, wenn man sie nicht anfordert

Mehrere Repositoriums-Routen liefern Knoten mit leerer `properties`-Abbildung,
solange die Anfrage kein `propertyFilter=-all-` trägt. Die Bibliothek setzt es,
wo sie diese Routen aufruft; wer sie mit `repo.raw.request(...)` umgeht, muss es
selbst setzen — sonst hält man für fehlend, was bloß nicht angefordert war.

---

## 2. Die Fallen — worauf zu achten ist

Jede davon wurde gegen eine echte Instanz gemessen. Sie sind der Grund, warum
es diese Bibliothek gibt.

### 2.1 HTTP 200 heißt nicht, dass etwas gespeichert wurde

edu-sharing nimmt Schreibvorgänge an, die es dann verwirft. Wo diese
Bibliothek einen Schreibvorgang zurückliest — Eigenschaften, Rechte,
Beziehungen, Vorschläge —, wirft sie `SilentDropError`, statt Erfolg zu melden.
Nicht jeder wird zurückgelesen; die Referenz nennt die, die es nicht werden
(`repo.add_to_collection` kann es nicht).

```python
try:
    await node.update(title="Neu")
except SilentDropError as exc:
    exc.dropped        # ["cclom:title"] -- die Namen, nicht die Werte
```

**Wer über `repo.raw` schreibt, verliert das.** Dann selbst zurücklesen.

Bekannte Verwerfer: `relations.create(metadata=...)` (angenommen, nirgends
gespeichert) und Metadatensatz-Felder, die die Instanz nicht kennt.

### 2.2 `unresolved` ist keine Zierde

Ein Filterwert, den die Instanz nicht kennt, wird **nicht angewendet** — und
die Suche beantwortet eine weitere Frage als die gestellte.

```python
answer = await repo.flows.search("Zellen", subject="Bio")
answer["unresolved"]   # [{"field": "subject", "value": "Bio",
                       #   "suggestions": ["Biologie"]}]
```

Beim Schreiben genauso: `add_material` und `update_material` liefern
`unresolved` für Werte, die **nicht** geschrieben wurden. Das Material gibt es
dann ohne sie.

**Nie ein Ergebnis an einen Menschen oder ein Modell melden, ohne das geprüft
zu haben.**

### 2.3 `total_is_lower_bound`, `truncated`, `complete`

- `total_is_lower_bound=True` → `total` zählt *mindestens* so viele. Wer das
  als genaue Zahl meldet, behauptet eine Zahl, die keine ist.
- `browse_tree`/`search_in_collection`: `truncated=True` → in der Antwort
  fehlt etwas, das hineingehört — der Deckel darauf, wie viele Sammlungen
  geöffnet werden, eine Seite mit mehr Untersammlungen als
  `max_collections`, oder (nur `search_in_collection`) eine Sammlung, deren
  Material bei `limit` abgeschnitten wurde. Ein leeres Ergebnis heißt dann
  **nicht** „es gibt keins". Ein Zyklus und die gefragte `depth` sind keins
  von beidem: sie setzen nichts.
- `search_in_collection`: `truncated_by` nennt den Deckel — `"collections"`
  (dann `max_collections`/`depth` heben) oder `"material"` (dann `limit`).
  Und `searched` zählt **Sammlungen**; `materials_read` zählt, was
  tatsächlich verglichen wurde. Wer das erste für das zweite hält, hält
  eine Stichprobe für das Ganze.
- `collection_contents`: `collections_truncated=True` → die
  **Unter**sammlungen sind bei `limit` gedeckelt wie das Material. Lies es;
  eine gekürzte Liste sieht aus wie eine Sammlung mit weniger Kindern, als
  sie hat. Nennt der Endpunkt keine Gesamtzahl, ist `total_collections`
  dann eine untere Schranke und `total_materials` der `offset` plus das
  Gesehene.
- `collection_stats`: `complete=False` → die Aufschlüsselung ist eine
  Stichprobe.

`find_collections` setzt `total_is_lower_bound` immer: es führt zwei Routen
zusammen.

### 2.4 Eine Sammlung ist kein Ordner, und eine Suche lässt sich nicht darauf einschränken

- Sammlungen über `repo.create_collection` anlegen, nie als `ccm:map`-Knoten.
  Ein anders angelegter Knoten ist für den Rest des Systems keine Sammlung.
- Sammlungen bilden einen **Graphen**, keinen Baum — eine Sammlung kann
  mehrere Eltern haben. `browse_tree` läuft ihn **breitensuchend** ab und
  überspringt, was es schon geöffnet hat. Das ist **keine** Kürzung und
  setzt `truncated` nicht: im Baum fehlt nichts, es steht nur nicht
  zweimal da (gemessen 09.09.2026). Die gefragte `depth` ebenso wenig.
  Breitensuchend zu laufen ist das, was das Überspringen sicher macht:
  jede Sammlung wird zuerst über ihren kürzesten Weg erreicht.
  Tiefensuchend traf der Gang eine über den langen Weg, markierte sie
  ohne Resttiefe als gesehen und verlor alles dahinter — und die Antwort
  sagte `truncated=False` (R05).
- Es gibt keine auf eine Sammlung eingeschränkte Suche.
  `virtual:primaryparent_nodeid` antwortet mit HTTP 400, und es wäre ohnehin
  die falsche Antwort: eine kuratierte Sammlung hält *Referenzen* auf Knoten,
  deren primärer Elternteil woanders liegt. `search_in_collection` läuft ab und
  filtert lokal.
- `collection_contents` fragt **zwei** Routen. Nur das Material zu holen ließe
  eine Sammlung aus Untersammlungen leer aussehen.

### 2.5 Drei verschiedene Arten von Zugehörigkeit

| | Hält | Gelesen mit |
|---|---|---|
| Sammlung | Referenzen auf Material, das auch anderswo liegt | `collection_contents` |
| Serienobjekt | ein Dokument *unter* einem Material, ohne eigenes Leben | `child_objects` |
| Beziehung | zwei Materialien, die *nebeneinander* stehen | `relations` |

Ein Serienobjekt trägt seinen Dateinamen in `name` und **keinen eigenen
Titel** — `title` fällt auf `cm:name` zurück und liest sich gleich, `name` ist
also das Feld, das es meint. Für einen Schreibvorgang, der einen Titel erhalten
muss, gibt es `stored_title_of`: dieselbe Kette ohne diesen Rückfall.

Beziehungen pflegen die Gegenrichtung automatisch: `isPartOf` von der Folge
angelegt, und die Reihe meldet `hasPart`. Eine frische Beziehung ist
`approved=False` — `relations.approve(...)` setzt es.

### 2.6 Labels gegen URIs

`node.get("ccm:taxonid")` gibt die URI. `node.labels("ccm:taxonid")` gibt
„Mathematik". `SearchHit.labels` tut dasselbe. Die Ablauf-Ebene löst die Labels
in `fields` für Sie auf.

Facetten*werte* sind URIs und tragen kein Label — `FacetValue` hat nur `value`
und `count`.

Welche Kurznamen (`subject`, `level`, …) es gibt, wird **von der Instanz
gelesen**, nicht in der Bibliothek festgelegt: `repo.searcher.field_aliases`.

**Ein Label kann zu zwei Vokabularen gehören.** Am 31.08.2026 gegen die Staging
gemessen: 25 Fachlabels stehen sowohl in `discipline` (Schulfächer) als auch in
`hochschulfaechersystematik` (Hochschulfächer) — darunter `Biologie`, `Chemie`,
`Physik`. Eine Suche über das Label filtert auf **alle**, denn die halbe
Materialmenge zu finden und wie die ganze auszusehen ist eine falsche Antwort:

```python
await repo.vocab.resolve(prop, "Biologie")      # die erste — eine von zweien
await repo.vocab.resolve_all(prop, "Biologie")  # beide, so filtert die Suche
```

Geschrieben wird die erste, und zwar mit Absicht: ein Arbeitsblatt für Klasse 6
als Hochschulfach zu markieren ist eine Behauptung, keine Erweiterung. Wer die
Hälften trennen will, filtert zusätzlich nach `level`.

### 2.7 Blättern, Grenzen und Vorgaben, die stillschweigend kürzen

- `repo.people.members(group)` fragt 100 an (der Endpunkt selbst hat die Vorgabe
  10), und eine größere Gruppe wird ohne ein Wort gekürzt — es kommt keine
  Gesamtzahl zurück. `limit` erhöhen oder mit `offset` weiterlesen, bis eine
  Seite kurz ist.
- `collection_contents` braucht `propertyFilter=-all-`, um überhaupt
  Eigenschaften zu bekommen; die Bibliothek setzt es. Über `repo.raw` müssen
  Sie es selbst setzen.
- Die zwei Methoden des Extraktionsdienstes sind **nicht** gereiht: gemessen
  lieferte `simple` einen Artikel, wo `browser` ein Cookie-Banner lieferte.
  Bringt eine nichts, ist die andere der zweite Versuch.

### 2.8 Ein Rahmenwort ruiniert eine Anfrage

Über einen Pool von 60 Knoten gemessen: `"Bruchrechnung"` traf 0 Knoten,
`"die Bruchrechnung"` traf 43 — und diese 43 sind falsch. Im Deutschen steckt
der Artikel in gewöhnlichen Wörtern, einer machte aus einer richtigen Ablehnung
eine Trefferquote von 72 %. `rerank=True` weitet die Anfrage auf und bewertet
neu; das kostet mehrere Anfragen, also dafür, wenn die Anfrage von einem
Menschen oder einem Modell kommt, nicht für eine maschinell gebaute
Filteranfrage.

`rerank=True` und `offset` vertragen sich nicht — der Pool wird über die
Varianten zusammengeführt, ein Versatz darin bedeutete also nicht, was ein
Aufrufer erwartet.

### 2.9 Tote Indexeinträge

Gemessen: 4 von 25 Suchtreffern waren nicht mehr abrufbar. `describe_many`
meldet sie in `failed`, statt zu werfen — eine kürzere Liste als angefragt ist
so davon zu unterscheiden, dass es diese Knoten nicht gibt.

### 2.10 Die zwei Anbieter sind nicht austauschbar

Gemessen am 31.08.2026. `openai` bietet 132 Modelle und meldet keine
Auslastung; `academiccloud` bietet 15 und meldet `demand` 0 bis 23, was sich im
Minutentakt ändert. Beide haben `chat/completions` und `responses`. Nur OpenAI
hat `embeddings`, `moderations` und `images/generations` — die AcademicCloud
antwortet 404, und ihre Modelle erzeugen `text` und `thought`, sonst nichts.

Und „OpenAI hat es" heißt nicht „Sie können es benutzen". Gemessen am
21.09.2026 stehen zehn Bildmodelle in `/models`, abrechenbar sind zwei
(`gpt-image-1.5`, `chatgpt-image-latest`); der Rest antwortet
`503 Model pricing unavailable`, `dall-e-2` und `dall-e-3` eingeschlossen.
Beide Überlebenden sind GPT-Bildmodelle, die `response_format` nie annehmen
und immer base64 liefern — `GeneratedImage.url` ist hier also immer `None`,
und wer zuerst `url` liest, findet nichts.

`reasoning_effort` und `verbosity` wirken bei der gpt-5- und o-Serie und werden
von älteren OpenAI-Modellen mit 400 abgelehnt. Die AcademicCloud nimmt sie an
und ignoriert sie: gleicher Tokenverbrauch bei `low` und `high`. Ihr Hebel ist
`chat_template_kwargs`, das die Bibliothek für Qwen3 setzt.

Die Bibliothek stellt beide auf `low` und wendet sie nur an, wo sie wirken.
**Ein ausdrücklicher Wert wird nie für Sie verworfen** — er löst stattdessen
einen Fehler aus, denn eine Antwort ohne den gewünschten Aufwand sieht genauso
aus wie eine mit ihm.

Ein virtuelles Modell (`model=["a","b","c"]` oder ein Name aus
`virtual_models`) nimmt das am wenigsten ausgelastete davon. Das lohnt bei der
AcademicCloud; bei OpenAI wird daraus eine Ausweichkette in Ihrer Reihenfolge.

### 2.11 Auslastung abfragen, und wechseln statt warten

`demand` ändert sich im Minutentakt, deshalb wird die Modellliste 30 Sekunden
gemerkt. Stellen Sie das darauf ein, wie lange Ihr Prozess lebt:

```python
# async: BildungsAPI hat keine blockierende Fassade
# Ein Skript, das eine Minute läuft: einmal fragen.
api = BildungsAPI.from_env(models_cache_seconds=CACHE_FOREVER)
print((await api.load()).summary())      # ins Startprotokoll

# Ein Dienst, der einen Tag läuft: die 30 Sekunden stehen lassen. CACHE_FOREVER
# ließe ihn nach Zahlen von vor Stunden entscheiden.
```

`load()` liefert einen `LoadReport`. **Zuerst `reports_load` lesen** — bei
OpenAI steht dort `false`, es wird gar keine Auslastung gemeldet, und die
Rangfolge ist alphabetisch statt eine Aussage über Warteschlangen.

**Wechseln schlägt Warten, solange es wohin zu wechseln gibt.** Ein 503 ist
wiederholbar, also verbrauchte ein ausgelastetes Modell bisher das volle
`max_retries` — rund 17 s bei voreingestellter Wartezeit — während ein anderes
danebenstand. Ein Kandidat bekommt jetzt `retries_before_switching`
Wiederholungen (Vorgabe 1), solange ein weiterer da ist; der letzte behält das
volle Budget. `max_retries=0` heißt weiterhin genau ein Versuch je Modell: die
Stellschraube senkt nur.

Ein 429 ist der Fall, dem das nicht hilft — die AcademicCloud begrenzt den
Schlüssel, nicht das Modell, der nächste Kandidat scheitert also genauso
schnell.

### 2.12 Am blockierenden `Repository` blockiert alles

Jede Eigenschaft von `Repository` gibt etwas heraus, das blockiert. Das war
nicht immer so: bis zum 10.09.2026 gaben `repo.vocab`, `repo.searcher`,
`repo.collections` und `repo.nodes` die asynchronen Objekte unverändert
zurück, und ein Methodenaufruf darauf erzeugte aus blockierendem Code eine
Koroutine, die nie erwartet wurde — kein Fehler, keine Wirkung.
`repo.vocab.suggest` hatte gar keinen blockierenden Weg.

```python
repo = Repository(url, auth=cred)
repo.collections.find("Bruchrechnung")      # blockiert, liefert ein SearchResult
repo.vocab.suggest("ccm:taxonid", "ysik")   # seit dem 10.09.2026 ebenso
```

Die kürzeren Wege am Repositorium selbst gibt es weiterhin, und sie sind
weiterhin kürzer — ein Aufruf statt zwei:

| Schicht | Kürzer |
|---|---|
| `repo.nodes.get/create/children` | `repo.node()` / `repo.create_node()` / `repo.children()` |
| `repo.collections.find/create/update/add/remove` | `repo.find_collections()` / `repo.create_collection()` / `repo.update_collection()` / `repo.add_to_collection()` / `repo.remove_from_collection()` |
| `repo.searcher.search` | `repo.search()` |
| `repo.vocab.resolve` / `.resolve_all` | `repo.resolve()` / `repo.resolve_all()` |

Zwei Wachen halten das fest. Die eine geht jede öffentliche Fläche der
asynchronen Verbindung durch und weist eine Koroutine auf der blockierenden
zurück. Die andere ruft jede Methode dieser Flächen und weist eine Antwort
zurück, die asynchrone Methoden trägt — `repo.nodes.wrap(data)` gab bis zum
11.09.2026 den asynchronen `Node` heraus, und ein `update()` darauf war eine
Koroutine, die nie lief.

---

### 2.13 Ein Sammlungs-Listing liefert Referenz-IDs

Eine Sammlung hält **Referenzen**, keine Datensätze. `collection_contents`,
`search_in_collection` und jedes auf eine Sammlung bezogene Listing geben die
IDs dieser Referenzen zurück — der gewöhnliche Weg zu einer ID, kein
Sonderfall. Gegen Staging gemessen (02.09.2026): `/usage` antwortet einer
Referenz-ID mit leerer Liste und dem Original mit zwei Sammlungen; und ein
Schreibvorgang an eine Referenz wird auf der Referenz gespeichert und erreicht
den Datensatz nie (vom MCP am 17.08.2026 gemessen) — die Rückleseprobe merkt
es nicht, weil sie denselben Knoten liest.

Die Bibliothek löst das auf. `node.original_id` nennt den Datensatz (`None`
auf einem Original), `node.collections()` und `flows.placement` fragen für das
Original, und `update()`, `set_property()` und `add_keywords()` schreiben
dorthin und geben das **Original** mit gesetztem `redirected_from` zurück.
Löschen wird *nicht* umgeleitet: an einer Referenz verschwindet nur die
Referenz, das ist harmlos, und `flows.delete` sagt `is_reference`, damit klar
ist, welches von beiden ging.

```python
node = await repo.node(node_id=listing_id)
node.is_reference            # True
changed = await node.update(title="…")
changed.id                   # die ID des Originals, nicht listing_id
changed.redirected_from      # listing_id -- der Schreibvorgang wurde umgeleitet
```

---

### 2.14 Ein Skill ist ein Datensatz mit Inhaltsart — und der Metadatensatz entscheidet, ob man danach filtern kann

Skills sind gewöhnliche Datensätze, deren Inhaltsart „Anleitung" sagt und
deren angehängte Datei die `SKILL.md` ist. Gegen Staging gemessen
(02.09.2026): mit `mds_oeh` ist die Inhaltsart ein Suchkriterium und 34
Skills antworten; mit `-default-` weist das Repositorium das Kriterium zurück
(`ValidationError`, und die Meldung sagt warum). `EDU_SHARING_METADATASET=
mds_oeh` setzen oder `metadataset=` übergeben — `from_env()` liest die
Variable seit dem 02.09.2026.

Zwei weitere gemessene Fallen: die `SKILL.md` liest man mit `download()`,
weil `/textContent` für Markdown leer ist; und der Ordner eines Skills (seine
Begleitdateien) antwortete anonym mit 403 — `files_reason` sagt es, statt eine
leere Liste als „reist allein" auszugeben.

Alles, was eine Konvention benennt — die URIs der Inhaltsarten, wie ein
Registry-Dokument sich zu erkennen gibt, die Blockarten — ist
`SkillConventions`, ein Parameter mit WLOs `WLO_SKILLS` als Vorgabe. Ein
anderes Repositorium übergibt seine eigenen. Und das zurückkommende Markdown
ist hochgeladener Inhalt: vor dem Prompt mit `as_untrusted` rahmen.

```python
repo = AsyncRepository(url, metadataset="mds_oeh")
found = await repo.flows.find_skills("Fragen generieren")
doc = await repo.flows.skill(found["hits"][0]["id"])
doc["files_reason"]          # anonym "folder_unreadable"
```

### 2.15 Ein Datensatz ist nicht in dem Moment auffindbar, in dem er angelegt wurde

Der Suchindex hinkt dem Knotenspeicher nach. Gemessen auf Staging (02.09.2026):
ein per `add_material` angelegter Datensatz war über seine Adresse
(`find_by_url`, `ccm:wwwurl`) nach 5,3 Sekunden auffindbar, vorher nicht. Die
Dublettenprüfung in `add_material` kann also einen Datensatz, den derselbe
Prozess eben angelegt hat, nicht sehen, und `search` listet ihn noch nicht —
`repo.node(node_id)` schon, denn das liest den Knotenspeicher. Ein Import, der
dieselbe Adresse zweimal enthält, muss seine Eingabe selbst entdoppeln; ein
Test, der anlegt und dann sucht, muss warten.

### 2.16 Der Template-Modus — der Prompt liegt auf dem Server

`BapiTemplates` schickt Konfigurations-IDs, einen Kontext-Knoten und Werte; der
Prompt selbst steht im Metadatenset. Gemessen auf Staging (11.09.2026):

- **Eine unbekannte ID antwortet 500** — *Missing MDS AI configuration for id
  X*. Die Bibliothek macht daraus einen `ValidationError`, der die ID und das
  Metadatenset nennt, und wiederholt ihn nicht.
- **`{{var(X)|node(X)|-}}`** ist die gebräuchliche Syntax: zuerst Ihr Wert,
  sonst die Eigenschaft des Knotens — entschieden je Platzhalter. Die
  Schreibweise `{{node.x}}` aus der Spec kommt in keiner Konfiguration vor.
- **Eine limited-Wahl füllt `var(X_DISPLAYNAME)` nicht**, und genau das lesen
  die Prompts der Themenseiten: dort ändert eine Wahl nichts.
- **`respond` braucht eine Konfiguration für die Responses-API.** Die
  chat-Konfigurationen antworten dort 400.
- **Das Gateway arbeitet mit seinem eigenen Konto, nicht als `user`.** Ein
  privater Kontext-Knoten antwortet 403, auch wenn `user` seinen Eigentümer
  nennt; `qas` braucht Write für das Konto des Gateways auf jedem Knoten.
  Vorschläge werden unter diesem Konto angelegt (`admin@B-API`).
- **`suggest` und `qas` schreiben.** Keiner von beiden wird nach einer 502,
  einer 504 oder einer abgerissenen Verbindung wiederholt — das Ergebnis kann
  schon gespeichert sein. Eine Verbindung, die nie zustande kam, wird
  wiederholt: gesendet wurde nichts.

```python
# async: BapiTemplates hat keine blockierende Fassade
templates = BapiTemplates.from_env()
await templates.chat(["topic_page_ai_default", "topic_page_ai_chat_completion",
                      "topic_page_ai_text_widget"], context_node_id=collection_id)
```
