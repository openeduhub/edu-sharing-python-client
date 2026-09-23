# edu-sharing für Python

> *English version: [README.md](README.md).*

Python-Bibliothek für [edu-sharing](https://edu-sharing.com)-Repositorien und die
**b-api** (Bildungs-API, OpenEduHub) — **repository-agnostisch** und **async-first**.

> **Status: vor 1.0.** Lesen, Suchen und Schreiben stehen und sind gegen
> edu-sharing 11.0 geprüft — auch schreibend, gegen eine echte Instanz. Der
> Fahrplan steht in [`docs/ARCHITECTURE.de.md`](docs/ARCHITECTURE.de.md)
> ([englisch](docs/ARCHITECTURE.md)).

**Suchen Sie einen bestimmten Aufruf?**
[docs/REFERENCE.de.md](docs/REFERENCE.de.md) listet jeden öffentlichen Namen
mit Ein- und Ausgabe. Dieses README erklärt das Warum, die Referenz ist die
Nachschlagetabelle.


## Version 0.3.0: eigene Metadaten und weniger Anwendungscode

Eigene Metadatensets lassen sich über `MetadataProfile` konfigurieren: getrennte
Lese- und Schreibfelder, Filter-Kurznamen, Volltextkriterium und Materialtyp.
Ein explizites leeres Profil übernimmt keine WLO-Felder. Ohne Profil bleibt
`WLO_METADATA_PROFILE` als kompatible Vorgabe aktiv. Technische API-Felder wie
`cm:name` bleiben erhalten.

`repo.metadata` lädt und puffert MDS-Definitionen. `repo.vocab` kann Vokabulare
parallel vorladen, Labels in beide Richtungen auflösen und JSON-Snapshots mit
Scope- und Altersprüfung im Speicher übernehmen. Suche und optionales lokales
Reranking unterstützen `raw_filters`, `locale` und `strict=True`.

Drei neue Flows: `prepare_material` erstellt einen prüfbaren Entwurf,
`place_material` platziert vorhandenes Material mit Referenz-ID und Teilfehlern,
`collection_context` bündelt Beschreibung, Inhalte und Stichprobenstatistik.
[API und Migration](docs/REFERENCE.de.md#metadatenprofile-und-cache-030) ·
[Anwendungsabläufe](docs/FLOWS.de.md#neue-zusammengesetzte-abläufe-030) ·
[generisches Beispiel](docs/examples/24_generic_metadata.py) ·
[Beispiel für Vorbereitung und Kontext](docs/examples/25_prepare_context.py) ·
[Umsetzung und Prüfergebnisse](docs/audits/2026-09-14-functional-implementation.md).
Die Ergänzungen sind offline mit API-Mocks geprüft; zusätzliche Live-Instanzen
wurden für diese Version nicht verändert oder als verifiziert angenommen.

Version 0.3.0 ist umgesetzt und in `main` gemergt; der Release-Tag folgt erst nach der
Live-Abnahme aus dem Release-Ablauf unten, zu installieren ist also `main`.
Die älteren Tags `v0.1.0` und `v0.2.0` liegen im Entwicklungsrepositorium,
das unter *Autor* steht.


## Installieren

Die Bibliothek benötigt **Python 3.11 oder neuer**.

Das Paket ist derzeit **noch nicht auf PyPI veröffentlicht**. Es wird deshalb direkt aus dem Git-Repository installiert.

Es gibt zwei unterstützte Installationswege:

- **pip** — gehört zu einer normalen Python-Installation und ist für den Einstieg meist der einfachste Weg.
- **uv** — ein schneller Python-Paket- und Projektmanager, der sich besonders für Entwicklung und reproduzierbare Umgebungen eignet.

Für normale Anwendungen empfiehlt sich außerdem eine **virtuelle Python-Umgebung (`venv`)**. Dadurch bleiben der edu-sharing Python Client und seine Abhängigkeiten von anderen Python-Projekten getrennt.

### Voraussetzungen

Benötigt werden:

- Python 3.11 oder neuer
- Git
- pip oder uv

Die installierte Python-Version prüfen:

```bash
python --version
```

Beispiel:

```text
Python 3.12.10
```

Unter Windows kann alternativ der Python Launcher verwendet werden:

```powershell
py --version
```

Git prüfen:

```bash
git --version
```

Beispiel:

```text
git version 2.51.0.windows.1
```

Falls Python oder Git fehlen, zuerst installieren:

- Python: <https://www.python.org/downloads/>
- Git: <https://git-scm.com/downloads>

### Windows: Installation mit pip

Die folgenden Befehle sind für **PowerShell** gedacht.

Zuerst einen Projektordner anlegen:

```powershell
mkdir C:\dev\edu-sharing-test
cd C:\dev\edu-sharing-test
```

Eine virtuelle Python-Umgebung erstellen:

```powershell
python -m venv .venv
```

Falls unter Windows `python` nicht gefunden wird, funktioniert häufig stattdessen der Python Launcher:

```powershell
py -m venv .venv
```

Die Umgebung aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Danach sollte der PowerShell-Prompt ungefähr so aussehen:

```text
(.venv) PS C:\dev\edu-sharing-test>
```

Falls PowerShell die Ausführung von `Activate.ps1` verweigert, kann die Ausführungsrichtlinie nur für die aktuelle PowerShell-Sitzung angepasst werden:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Danach erneut aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Optional pip aktualisieren:

```powershell
python -m pip install --upgrade pip
```

Jetzt den aktuellen Stand des edu-sharing Python Clients aus dem `main`-Branch installieren:

```powershell
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

Die benötigten Laufzeit-Abhängigkeiten, darunter `httpx` und `attrs`, werden automatisch mitinstalliert.

### Windows: Installation mit uv

Wer bereits `uv` verwendet, kann dieselbe Bibliothek damit installieren.

Projektordner und virtuelle Umgebung anlegen:

```powershell
mkdir C:\dev\edu-sharing-test
cd C:\dev\edu-sharing-test
uv venv
```

Die Umgebung aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Dann installieren:

```powershell
uv pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

`pip` und `uv` installieren dieselbe Bibliothek; nur das Werkzeug zur Verwaltung der Python-Umgebung und Pakete unterscheidet sich.

### Linux und macOS: Installation mit pip

Projektordner anlegen:

```bash
mkdir -p ~/edu-sharing-test
cd ~/edu-sharing-test
```

Virtuelle Umgebung erstellen und aktivieren:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Optional pip aktualisieren:

```bash
python -m pip install --upgrade pip
```

Client installieren:

```bash
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Linux und macOS: Installation mit uv

```bash
mkdir -p ~/edu-sharing-test
cd ~/edu-sharing-test
uv venv
source .venv/bin/activate
uv pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Installation prüfen

Nach der Installation lässt sich direkt testen, ob Python die Bibliothek findet:

```bash
python -c "from edusharing import Repository; print('edu-sharing Python Client erfolgreich installiert')"
```

Die Ausgabe sollte sein:

```text
edu-sharing Python Client erfolgreich installiert
```

Damit ist zunächst nur die lokale Paketinstallation geprüft. Im nächsten Schritt wird die Verbindung zu einem echten Repositorium getestet.

### Verbindung gegen die Staging-Instanz testen

Für einen einfachen lesenden Test kann die öffentliche Staging-Instanz verwendet werden:

```text
https://repository.staging.openeduhub.net
```

Für diesen Test werden **keine Zugangsdaten** benötigt.

Im Projektordner eine Datei `test_connection.py` anlegen:

```python
from edusharing import Repository


REPOSITORY_URL = "https://repository.staging.openeduhub.net"


with Repository(REPOSITORY_URL) as repo:
    about = repo.about()
    who = repo.whoami()

    print("Verbindung erfolgreich")
    print("Repository-Version:", about.repository_version)
    print("Plugins:", about.plugins)
    print("Aktueller Benutzer:", who.authority)
```

Anschließend ausführen:

```bash
python test_connection.py
```

Eine erfolgreiche Verbindung liefert beispielsweise:

```text
Verbindung erfolgreich
Repository-Version: 11.0
Plugins: [...]
Aktueller Benutzer: esguest
```

`esguest` bedeutet, dass der Zugriff anonym erfolgt.

Mit diesem Test werden Paketimport, HTTPS-Verbindung, Erreichbarkeit der Staging-Instanz, API-Antwort und anonymer Lesezugriff geprüft.

### Suche gegen Staging testen

Als zweiten Test kann eine echte Suche ausgeführt werden. Eine Datei `test_search.py` anlegen:

```python
from edusharing import Repository


REPOSITORY_URL = "https://repository.staging.openeduhub.net"


with Repository(REPOSITORY_URL, metadataset="mds_oeh") as repo:
    ergebnis = repo.search(
        "Photosynthese",
        subject="Biologie",
        limit=5,
    )

    print(f"Gefundene Ergebnisse: {ergebnis.total}")

    for treffer in ergebnis.hits:
        print()
        print("Titel:", treffer.title)
        print("URL:", treffer.url)
```

Ausführen:

```bash
python test_search.py
```

`mds_oeh` wird hier bewusst als Metadatensatz gewählt, weil der Filter `subject="Biologie"` dort verfügbar ist.

Wenn Treffer zurückkommen, ist der Client installiert, die Verbindung funktioniert und eine echte Suche gegen edu-sharing wurde erfolgreich ausgeführt.

### Zugangsdaten verwenden

Für öffentliche Lesezugriffe sind je nach Repositorium keine Zugangsdaten erforderlich. Schreibende oder geschützte Operationen benötigen dagegen ein edu-sharing-Konto.

Zugangsdaten können direkt übergeben werden:

```python
from edusharing import Repository


with Repository(
    "https://repository.example.org",
    auth=("benutzer", "passwort"),
) as repo:
    print(repo.whoami())
```

Für Anwendungen und Entwicklungsumgebungen empfiehlt sich die Verwendung von Umgebungsvariablen:

```text
EDU_SHARING_URL
EDU_SHARING_USER
EDU_SHARING_PASSWORD
EDU_SHARING_METADATASET
```

Unter Windows PowerShell zum Beispiel:

```powershell
$env:EDU_SHARING_URL="https://repository.example.org"
$env:EDU_SHARING_USER="benutzer"
$env:EDU_SHARING_PASSWORD="passwort"
$env:EDU_SHARING_METADATASET="mds_oeh"
```

Zugangsdaten sollten **nicht in die URL geschrieben werden**:

```text
https://benutzer:passwort@repository.example.org
```

Der Client lehnt diese Form bewusst ab, weil URLs in Logs und Fehlermeldungen auftauchen können.

### Bestehende Installation aktualisieren

Mit pip:

```bash
python -m pip install --upgrade "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

Mit uv:

```bash
uv pip install --upgrade "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Eine bestimmte Version installieren

Der aktuelle Tag ist `v0.3.5`:

```bash
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@v0.3.5"
```

`@main` oben folgt dem, was seither dazugekommen ist. Jeder frühere Tag ab `v0.0.1`
liegt hier wie im
Entwicklungsrepositorium unter [*Autor*](#autor), das denselben `main` und die
ganze Geschichte trägt; wie ein Tag hierherkommt, sagt der Release-Ablauf am
Ende dieser Datei.

> **Nicht `@v0.1.0`, woher auch immer.** Dieser Tag stammt aus der Zeit vor
> mehreren Prüfrunden und kennt weder die Metadatenprofile noch die
> zusammengesetzten Flows.

### Entwicklungsinstallation aus einer lokalen Arbeitskopie

Wer am Client selbst entwickeln, die Tests ausführen oder die Beispiele aus dem Repository verwenden möchte, sollte das Repository lokal klonen:

```bash
git clone https://github.com/openeduhub/edu-sharing-python-client.git
cd edu-sharing-python-client
```

Mit pip unter Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Mit pip unter Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

`-e` steht für eine **editable installation**. Änderungen am lokalen Quellcode stehen dadurch unmittelbar in der Python-Umgebung zur Verfügung, ohne das Paket nach jeder Änderung neu installieren zu müssen.

Mit uv wird die vollständige Entwicklungsumgebung einschließlich der für Tests und Beispiele benötigten Abhängigkeiten installiert:

```bash
uv sync
```

Alternativ kann eine editable installation explizit ausgeführt werden:

```bash
uv pip install -e .
```

### Tests ausführen

Die Offline-Tests laufen deterministisch und benötigen keine Verbindung zu einer edu-sharing-Instanz:

```bash
uv run pytest
```

Live-Tests gegen die Staging-Instanz unter Linux/macOS:

```bash
EDU_SHARING_URL=https://repository.staging.openeduhub.net uv run pytest -m live
```

Unter Windows PowerShell:

```powershell
$env:EDU_SHARING_URL="https://repository.staging.openeduhub.net"
uv run pytest -m live
```

Die schreibenden Tests (`-m write`) benötigen gültige Zugangsdaten. Sie arbeiten ausschließlich in einem eigenen Wegwerf-Ordner, den sie selbst anlegen und wieder entfernen.

### Lokale Arbeitskopie aktualisieren

Zuerst die Git-Arbeitskopie aktualisieren:

```bash
git pull
```

Bei einer pip-Entwicklungsinstallation kann die editable installation erneut ausgeführt werden, wenn sich Paket-Metadaten oder Abhängigkeiten geändert haben:

```bash
python -m pip install -e .
```

Mit uv:

```bash
git pull
uv sync
```

### Fehlerbehebung

**`python` wird unter Windows nicht gefunden**

Zuerst den Python Launcher ausprobieren:

```powershell
py --version
```

Falls das funktioniert, können `py -m venv .venv` und `py -m pip ...` verwendet werden. Falls auch `py` nicht gefunden wird, muss Python 3.11 oder neuer installiert werden.

**`git` wird nicht gefunden**

Prüfen:

```powershell
git --version
```

Falls Git nicht installiert ist, Git von <https://git-scm.com/downloads> installieren und PowerShell beziehungsweise das Terminal neu öffnen.

**PowerShell kann `Activate.ps1` nicht ausführen**

Nur für die aktuelle PowerShell-Sitzung:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**`ModuleNotFoundError: No module named 'edusharing'`**

Prüfen, ob die virtuelle Umgebung aktiv ist, und anschließend den Import direkt testen:

```bash
python -c "from edusharing import Repository; print('OK')"
```

Falls das nicht funktioniert, die Installation mit pip oder uv über die oben genannten Befehle erneut ausführen.

**Installation funktioniert, aber Staging ist nicht erreichbar**

Zuerst nur den lokalen Import testen:

```bash
python -c "from edusharing import Repository; print('OK')"
```

Funktioniert dieser Befehl, aber `python test_connection.py` nicht, ist die Bibliothek korrekt installiert. Das Problem liegt dann wahrscheinlich bei Netzwerk oder Repository-Verbindung. Unternehmens-Proxys, VPNs, Firewalls oder TLS-Inspection können verhindern, dass Python die Staging-Instanz erreicht.


## Schnellstart

```python
from edusharing import Repository

with Repository("https://repository.staging.openeduhub.net",
                metadataset="mds_oeh") as repo:
    treffer = repo.search("Photosynthese", subject="Biologie", limit=5)
    for hit in treffer.hits:
        print(hit.title, hit.url)
```

Mehr ist es nicht: zum Lesen keine Zugangsdaten, und `subject="Biologie"`
statt einer Vokabular-URI. `metadataset="mds_oeh"` ist das, was den Filter
möglich macht — gemessen antwortet der Standard-Metadatensatz darauf mit
`400`, denn ob eine Eigenschaft filterbar ist, ist eine Eigenschaft des
Metadatensatzes und nicht der Eigenschaft selbst.

`AsyncRepository` ist dieselbe Fläche mit `await` vor jedem Aufruf.

## Inhalt

- [Version 0.3.0: eigene Metadaten und weniger Anwendungscode](#version-030-eigene-metadaten-und-weniger-anwendungscode)
- [Installieren](#installieren)
  - [Voraussetzungen](#voraussetzungen)
  - [Windows: Installation mit pip](#windows-installation-mit-pip)
  - [Windows: Installation mit uv](#windows-installation-mit-uv)
  - [Linux und macOS: Installation mit pip](#linux-und-macos-installation-mit-pip)
  - [Linux und macOS: Installation mit uv](#linux-und-macos-installation-mit-uv)
  - [Installation prüfen](#installation-prüfen)
  - [Verbindung gegen die Staging-Instanz testen](#verbindung-gegen-die-staging-instanz-testen)
  - [Suche gegen Staging testen](#suche-gegen-staging-testen)
  - [Zugangsdaten verwenden](#zugangsdaten-verwenden)
  - [Bestehende Installation aktualisieren](#bestehende-installation-aktualisieren)
  - [Eine bestimmte Version installieren](#eine-bestimmte-version-installieren)
  - [Entwicklungsinstallation aus einer lokalen Arbeitskopie](#entwicklungsinstallation-aus-einer-lokalen-arbeitskopie)
  - [Tests ausführen](#tests-ausführen)
  - [Lokale Arbeitskopie aktualisieren](#lokale-arbeitskopie-aktualisieren)
  - [Fehlerbehebung](#fehlerbehebung)
- [Schnellstart](#schnellstart)
- [Warum](#warum)
- [Was heute geht](#was-heute-geht)
  - [Woher ein Name kommt](#woher-ein-name-kommt)
  - [Suchen mit Labels statt URIs](#suchen-mit-labels-statt-uris)
  - [Sammlungen](#sammlungen)
  - [Schreiben — mit Rückleseprobe](#schreiben--mit-rückleseprobe)
  - [Für KI-Anwendungen](#für-ki-anwendungen)
  - [Den Skill im eigenen Werkzeug nutzen](#den-skill-im-eigenen-werkzeug-nutzen)
  - [Das LLM-Gateway](#das-llm-gateway)
  - [Der Template-Modus — Prompts, die auf dem Server liegen](#der-template-modus--prompts-die-auf-dem-server-liegen)
  - [Der Extraktionsdienst — Text, den das Repositorium nicht hat](#der-extraktionsdienst--text-den-das-repositorium-nicht-hat)
  - [Der Metadata Agent — was in den JSON einer Inhaltsart gehört](#der-metadata-agent--was-in-den-json-einer-inhaltsart-gehört)
  - [Abläufe — ein Anwendungsfall, ein Aufruf](#abläufe--ein-anwendungsfall-ein-aufruf)
- [Wohin es geht](#wohin-es-geht)
- [Was die Bibliothek für dich weiß](#was-die-bibliothek-für-dich-weiß)
  - [Veröffentlichen — der Schritt, den edu-sharing nicht tut](#veröffentlichen--der-schritt-den-edu-sharing-nicht-tut)
  - [Wenn ein Schreibvorgang halb glückt](#wenn-ein-schreibvorgang-halb-glückt)
  - [Bewertungen und Kommentare](#bewertungen-und-kommentare)
  - [Vorschlagen statt schreiben, und zur Prüfung weiterreichen](#vorschlagen-statt-schreiben-und-zur-prüfung-weiterreichen)
  - [Vorschaubilder, Blättern, Sammlung umbenennen](#vorschaubilder-blättern-sammlung-umbenennen)
  - [Gruppen — wer moderieren darf](#gruppen--wer-moderieren-darf)
  - [Wo ein Knoten liegt — und wer ihn kuratiert hat](#wo-ein-knoten-liegt--und-wer-ihn-kuratiert-hat)
  - [Serienobjekte — Dokumente, die zu einem Material gehören](#serienobjekte--dokumente-die-zu-einem-material-gehören)
  - [Relationen — Knoten, die zusammengehören](#relationen--knoten-die-zusammengehören)
  - [Kuratierte Seiten — was eine Sammlung rendert](#kuratierte-seiten--was-eine-sammlung-rendert)
  - [Was diese Bibliothek nicht tut](#was-diese-bibliothek-nicht-tut)
- [Felder und Dateien, die keine Kurznamen haben](#felder-und-dateien-die-keine-kurznamen-haben)
- [Beispiele](#beispiele)
- [Aufbau](#aufbau)
- [Generierte Schicht neu bauen](#generierte-schicht-neu-bauen)
- [Protokoll](#protokoll)
- [Tests](#tests)
- [Veröffentlichen](#veröffentlichen)
- [Sicherheit](#sicherheit)
- [Autor](#autor)
- [Lizenz](#lizenz)


## Warum

edu-sharing hat 318 REST-Pfade und ein Verhalten, das man nicht raten kann: welcher
Schreibweg für welche Property gilt, dass ein `200 OK` **kein** Persistenzbeweis ist,
dass es zwei Sammlungs-Suchen gibt und keine die Obermenge der anderen ist. Diese
Bibliothek kapselt das gemessene Verhalten, damit Dritte es nicht neu herausfinden
müssen.

**Repository-agnostisch** heißt: Vokabulare werden zur Laufzeit gegen den
Metadatensatz *der jeweiligen Instanz* aufgelöst, nicht gegen eine eingebaute
Tabelle. `subject="Biologie"` funktioniert damit auch auf einem Repositorium, das
nichts mit WirLernenOnline zu tun hat.

## Was heute geht

```python
from edusharing import Repository

with Repository("https://repository.staging.openeduhub.net") as repo:
    about = repo.about()
    print(about.repository_version)   # 11.0
    print(about.plugins)              # ['mongo-plugin', 'b-api', ...]

    wer = repo.whoami()               # als wer laufe ich hier?
    print(wer.authority)              # 'esguest' = anonym
```

"Dieselbe Oberfläche" ist wörtlich gemeint, und seit dem 10.09.2026 stimmt
das auch: bis dahin gaben `repo.vocab`, `repo.searcher`, `repo.collections`
und `repo.nodes` die asynchronen Objekte heraus, ein blockierender Aufrufer
bekam also eine Koroutine, die nichts tat. Eine Wache geht jetzt jede
öffentliche Fläche durch und weist eine zurück.

`AsyncRepository` ist dieselbe Oberfläche für asynchronen Code; der synchrone
Zugang funktioniert auch im Notebook, wo bereits ein Event-Loop läuft.

Zugangsdaten kommen aus der Umgebung (`EDU_SHARING_URL`, `EDU_SHARING_USER`,
`EDU_SHARING_PASSWORD`, optional `EDU_SHARING_METADATASET`) oder direkt:

```python
repo = Repository(url, auth=("benutzer", "passwort"))
```

Zugangsdaten in der Adresse (`https://benutzer:passwort@host`) werden
abgewiesen: eine Adresse steht im Log und in jeder Fehlermeldung, sie kämen
mit. `auth=` und die Umgebung sind der Ort dafür.

Jeder der 389 Endpunkte ist erreichbar, auch ohne eigene Methode:

```python
werte = repo.raw.json("GET", "/config/v1/values")
```

### Woher ein Name kommt

Fast alles ist ein einziger Import:

```python
from edusharing import Repository, Node, SearchResult, NotFoundError
```

| Import | Was dort liegt |
|---|---|
| `from edusharing import …` | das Repositorium, seine Ergebnisse, seine Fehler |
| `edusharing.agent` | Bausteine für KI-Anwendungen: Sicherheit, Bereinigung, Formatierung |
| `edusharing.bapi` | das LLM-Gateway — ein eigener Dienst, in beiden Modi: `BildungsAPI` und `BapiTemplates` |
| `edusharing.extraction` | der Extraktionsdienst — ebenso |
| `edusharing.metadata_agent` | der Metadata Agent — ebenso |

Die Flows brauchen keinen eigenen Import: sie hängen an einer Verbindung, als
`repo.flows.search(...)`. Die drei Nachbardienste bekommen ein eigenes Modul,
weil sie eine eigene Adresse haben — eine Verbindung zu einem Repositorium sagt
nichts darüber, ob es sie gibt.

### Suchen mit Labels statt URIs

```python
with Repository(url, metadataset="mds_oeh") as repo:
    ergebnis = repo.search("Photosynthese", subject="Biologie", limit=5)

    for offen in ergebnis.unresolved:   # nicht auflösbare Filter — nie stumm
        print("!", offen)               # "ccm:taxonid='Bio' — gemeint: Biologie?"

    for treffer in ergebnis.hits:
        print(treffer.title, treffer.labels("ccm:taxonid"), treffer.url)
```

`subject="Biologie"` wird gegen den Metadatensatz **dieser** Instanz aufgelöst, nicht
gegen eine eingebaute Tabelle. Welche Metadatensätze es gibt, sagt
`repo.metadatasets()`; die Wahl ändert, was filterbar ist und was gefunden wird.

Facetten zählen serverseitig über die ganze Ergebnismenge:

```python
ergebnis = repo.search("Photosynthese", facets=["ccm:educationalcontext"])
for wert in ergebnis.facets[0].values:
    print(wert.count, wert.value)
```

**Als Ablauf:** `repo.flows.search("Photosynthese", subject="Biologie")`
sendet dieselben zwei Anfragen und antwortet mit einem `dict`;
`repo.flows.vocabulary("subject")` sagt, was ein Feld annimmt.

### Sammlungen

```python
repo.find_collections("Optik")
```

Fragt **beide** Sammlungs-Suchen von edu-sharing gleichzeitig ab und führt sie
zusammen — keine ist Obermenge der anderen. Bei „Deutsch" ist ihre Schnittmenge
gemessen **null**.

Zum Ausprobieren: `python docs/examples/01_connect.py` und `02_search.py`

**Als Ablauf:** `repo.flows.find_collections("Optik")`, und
`repo.flows.collection_contents(collection_id)`, um eine zu öffnen.

### Schreiben — mit Rückleseprobe

```python
node = repo.node("abc-123")
node = node.update(title="Neuer Titel")     # zurückgelesen, wirft bei stillem Verlust
node = node.add_keywords("Weimar (Ort)")    # ergänzt, ersetzt nicht
node = node.content.upload(daten, filename="material.pdf", mimetype="application/pdf")
```

Warum das nicht trivial ist: **edu-sharing meldet `200 OK` für Schreibvorgänge,
die nicht stattgefunden haben.** Eine Property, die der Metadatensatz nicht
kennt, wird stillschweigend verworfen — Statuscode 200, Wert weg. `update()`
liest deshalb zurück:

```
SilentDropError: Nicht gespeichert: ccm:oeh_collection_compendium_text
  (HTTP 200, nach der Rückleseprobe abwesend oder abweichend). Zwei übliche
  Ursachen: die Property ist im Metadatensatz dieser Instanz nicht vorgesehen,
  oder das Schreibrecht fehlt. node.set_property(...) umgeht die Filterung
  des Metadatensatzes.
```

Auf `set_property` weicht die Bibliothek **nicht** von selbst aus: die Filterung
ist eine Entscheidung des Repositoriums, keine Panne. Sie zu umgehen bleibt ein
bewusster Schritt.

Sammlungen:

```python
sammlung = repo.create_collection("Meine Sammlung")   # privat per Vorgabe
repo.add_to_collection(sammlung.id, node.id)          # Referenz, keine Kopie
```

Zum Ausprobieren: `python docs/examples/03_write.py` — legt einen eigenen
Wegwerf-Ordner an und entfernt ihn wieder.

**Als Ablauf:** `repo.flows.add_material(…)` und
`repo.flows.update_material(…)` — dieselben Anfragen, ein `dict` zurück.
`10_two_levels.py` lässt beide Fassungen nebeneinander laufen und zählt mit.

### Für KI-Anwendungen

`edusharing.agent` ist framework-neutral — kein MCP-, kein LangChain-Import:

```python
# async: as_result nimmt ein Awaitable, also AsyncRepository
from edusharing.agent import as_result, as_untrusted, format_results, is_safe_url

ergebnis = await as_result(                      # Fehler als Ergebnis, nicht als Exception
    repo.search("Photosynthese", subject="Biologie"),
    format=lambda r: format_results(r, max_chars=1500),
)
print(ergebnis.text)                             # id und url überleben jedes Budget

if is_safe_url(hit.source_url):                  # SSRF: URLs aus Fremddaten
    ...
prompt = as_untrusted(hit.description,           # unsichtbare Steuerzeichen raus,
                      label=f"Material {hit.id}")  # als Fremdmaterial gekennzeichnet
```

Und vor dem Schreiben erst zeigen, was passieren würde:

```python
# async: plan_update und apply() sind Koroutinen
from edusharing.agent import plan_update

plan = await plan_update(node, title="Neuer Titel")
print(plan.describe())        # eine Zeile je Änderung: "cclom:title: Alt  ->  Neuer Titel"
if plan.has_changes:
    node = await plan.apply()
```

### Den Skill im eigenen Werkzeug nutzen

**Ein Skill für Coding-Agenten liegt der Bibliothek bei.**
[`.claude/skills/edu-sharing-python/`](.claude/skills/edu-sharing-python/SKILL.de.md)
bringt einem Modell bei, jeden Teil der Bibliothek ohne Vorkenntnisse zu
benutzen: Installieren und Verbinden, Rezepte mit lauffähigem Code und der Form
dessen, was zurückkommt, jeden Aufruf mit seinen Parametern, die Fehler und die
gemessenen Fallen. Sein Ordner `reference/` trägt die Referenz, den
Ablauf-Leitfaden, die Fallen und alle Beispiele dieses Repositoriums mit, damit
er auch außerhalb davon trägt. Er liegt auf
[deutsch](.claude/skills/edu-sharing-python/SKILL.de.md) und
[englisch](.claude/skills/edu-sharing-python/SKILL.md) vor.

In diesem Repositorium ist er für jeden Agenten schon aktiv. Für überall sonst
den Ordner kopieren — das Paket installiert ihn nicht:

| Werkzeug | Wohin der Ordner kommt |
|---|---|
| Claude Code, für einen selbst | `~/.claude/skills/edu-sharing-python/` |
| Claude Code, für ein Projekt | `<projekt>/.claude/skills/edu-sharing-python/` |
| OpenAI Codex, für einen selbst | `~/.agents/skills/edu-sharing-python/` |
| OpenAI Codex, für ein Repositorium | `<repo>/.agents/skills/edu-sharing-python/` |
| claude.ai | `dist/edu-sharing-python.zip` als Skill hochladen |

```bash
cp -r .claude/skills/edu-sharing-python ~/.claude/skills/    # Claude Code
cp -r .claude/skills/edu-sharing-python ~/.agents/skills/    # OpenAI Codex
python scripts/build_skill_zip.py                             # claude.ai
```

Beide Werkzeuge finden den Skill über seine Beschreibung; beim Namen rufen ihn
Claude Code mit `/edu-sharing-python`, Codex mit `$edu-sharing-python`. Eine
Kopie folgt dem Repositorium nicht — nach einer Aktualisierung neu kopieren. Die
ZIP hat den Skill-Ordner als Wurzel und nur den ersten Satz der Beschreibung,
weil claude.ai höchstens 200 Zeichen nimmt; der Upload selbst ist hier nicht
geprüft. In claude.ai hilft der Skill beim Schreiben des Codes — ausgeführt wird
er dort, wo das Repositorium erreichbar ist, meist nicht in der Sandbox von
claude.ai.

Tests halten **beide** Sprachfassungen an der Bibliothek: jeder Ablauf genannt,
jeder Aufruf mit seinen Parametern gezeigt, kein Aufruf erfunden, keine
Umgebungsvariable, die der Code nicht liest, kein Verweis aus dem Ordner
hinaus. Die Kopien in `reference/` hält `scripts/sync_skill.py` gleich mit
`docs/`.

### Das LLM-Gateway

```python
# async: BildungsAPI hat keine blockierende Fassade
from edusharing.bapi import BildungsAPI

async with BildungsAPI.from_env() as llm:        # B_API_KEY und B_API_BASE_URL
    antwort = await llm.chat("Fasse zusammen: …")
    print(llm.last_model)                        # wessen Antwort war das?
```

**Beide Variablen, und es gibt keine Vorgabe-Adresse.** Bis zum 28.08.2026 fiel
dieser Client auf ein Staging-Gateway zurück — wer nur `B_API_KEY` setzte,
schickte seinen Schlüssel damit an einen Host, den er nicht gewählt hatte.
`TextExtraction` daneben hat genau das seit jeher verweigert; die beiden Dienste
widersprachen sich in derselben Bibliothek. Der Schlüssel reist als
`X-API-KEY`, nicht als Bearer-Token.

Ohne feste Modell-ID wird das am wenigsten ausgelastete bereite Textmodell
gewählt — und bei Bedarf das nächste: `status: ready` heißt nicht, dass ein
Modell antwortet. Die Eigenheiten der Modellfamilien (`max_completion_tokens`
für GPT-5/o, abgeschaltetes Denken bei Qwen3 — aber nicht bei Mistral) stecken
in `bapi.body`; welches Modell zu nehmen ist, in `bapi.models`.

**Das Gateway reicht die OpenAI-Oberfläche durch**, nicht nur Chat:

```python
# async: das Gateway hat keine blockierende Fassade
vektoren = await llm.embeddings(["Photosynthese", "Zellatmung"],
                                model="text-embedding-3-small", provider="openai")
urteil = await llm.moderate(text, model="omni-moderation-latest",
                            provider="openai")    # .flagged, .categories, .scores
bilder = await llm.images("ein Baum", model="gpt-image-1.5")  # .b64, .raw
audio = await llm.call_bytes(
    "audio/speech", {"model": "gpt-4o-mini-tts", "input": text, "voice": "alloy"},
    provider="openai", max_bytes=10 * 1024 * 1024)
gesprochen = await llm.call_multipart(      # die vier Routen mit einer Datei
    "audio/transcriptions", {"model": "gpt-4o-mini-transcribe"},
    file=audio, filename="probe.mp3", provider="openai")
```

**Diese IDs rechnet das Gateway ab, und das ist nicht dasselbe wie die, die es
führt.** Gemessen am 21.09.2026 antworten `dall-e-2`, `dall-e-3`, `tts-1`,
`whisper-1` und acht der zehn Bildmodelle mit `503 Model pricing unavailable`
— nirgends bedient, nirgends angekündigt. Die beiden abrechenbaren
Bildmodelle sind GPT-Bildmodelle, die `response_format` nie nehmen und immer
base64 liefern: `GeneratedImage.url` ist hier also `None`, das Bild steht in
`.b64`, und `.raw` trägt, was die Antwort über Größe, Güte und Verbrauch
sagte — ein zweiter Blick darauf kostet ein zweites Bild. `call_multipart` ist
der einzige Weg zu `audio/transcriptions`, `audio/translations`,
`images/edits` und `files`: die nehmen eine Datei statt eines JSON-Körpers,
also erreicht `call` keine davon.

Hier wird kein Modell geraten — `chat()` darf das, weil eine gemessene Politik
dahintersteht, und für diese gibt es keine. **Der Anbieter entscheidet, was
möglich ist:** gemessen am 28.08.2026 führt `academiccloud` 16 Modelle, keines
davon für Einbettung oder Moderation, `openai` dagegen 132 einschließlich beider.

Die Endpunktliste ist gemessen, nicht gelesen. `/v3/api-docs` selbst beschreibt
nur die eigenen Controller des Gateways; die OpenAI-Routen stehen in Gruppen je
Anbieter (`/v3/api-docs/openai`, `/v3/api-docs/academiccloud`), und die
beschreiben die OpenAI-Oberfläche statt dessen, was geht — die der AcademicCloud
nennt `/embeddings`, das dort 404 antwortet. Ein leerer Rumpf an jede
Kandidatenroute trennt sie — `403` heißt, das Gateway reicht die Route gar nicht
durch, alles andere heißt doch.
Auf der Liste: `chat/completions`, `completions`, `embeddings`, `moderations`,
`responses`, `images/generations`, `images/edits`, `audio/*`, `files`,
`batches`, `fine_tuning/jobs`, `vector_stores`. **Nicht** darauf: `rerank`.

Zum Ausprobieren: `python docs/examples/04_agent_blocks.py` und `20_provider_load.py`

### Der Template-Modus — Prompts, die auf dem Server liegen

Dasselbe Gateway läuft auf eine zweite Art. Dort ist der Prompt eine
Konfiguration im Metadatenset — die Themenseiten nutzen sie —, und Sie schicken
nur ihre ID, einen Kontext-Knoten und, wenn Sie wollen, Werte zum Einsetzen.
`BapiTemplates` ist sein Client: Er braucht kein `BildungsAPI`, und
`BildungsAPI` ändert sich nicht, weil es ihn gibt.

```python
# async: BapiTemplates hat keine blockierende Fassade
from edusharing.bapi import BapiTemplates

async with BapiTemplates.from_env() as templates:   # + EDU_SHARING_METADATASET
    text = await templates.chat(
        ["topic_page_ai_default", "topic_page_ai_chat_completion",
         "topic_page_ai_text_widget"],
        context_node_id=collection_id)
```

**Welcher Modus wann.** Der Proxy, wenn Ihr Code den Prompt besitzt. Der
Template-Modus, wenn das Repositorium ihn besitzen soll: derselbe Text für
jeden Aufrufer, geändert ohne Release, gefüllt aus dem Knoten selbst.

**Freier Text landet so im Prompt, wie er ist.** Gemessen am 11.09.2026 hat ein
Wert, der „ignoriere alle bisherigen Anweisungen" sagte, die Antwort umgelenkt.
Für Eingaben, denen Sie nicht trauen, gibt es `chat_limited` und seine
Geschwister: Sie schicken Paare `{widget_id: value_id}`, und freier Text, dort
übergeben, hat den Prompt nicht erreicht.

**Das Gateway arbeitet mit seinem eigenen Konto.** Ein privater Kontext-Knoten
antwortet 403, gleich, wen `user` nennt. `suggest` legt seine Vorschläge unter
diesem Konto am Knoten ab — prüfen mit `node.suggestions`, übernehmen mit
`repo.flows.accept_suggestion`.

Der Rest — die Fehlertabelle, `respond`, `qas`, was eine limited-Wahl nicht
füllt — steht in [docs/REFERENCE.de.md](docs/REFERENCE.de.md) unter *Der
Template-Modus*.

Zum Ausprobieren: `python docs/examples/22_bapi_templates.py`, und
`23_ai_suggestions.py` fürs Vorschlagen und Übernehmen — es schreibt, in einem
eigenen Wegwerf-Ordner.

### Der Extraktionsdienst — Text, den das Repositorium nicht hat

Ein Repositorium kann bereits extrahierten Text zu einem Material enthalten.
Für eine neue Webseite oder fehlenden Volltext bieten manche Installationen
einen eigenen Textextraktionsdienst. Er liefert Klartext oder Markdown und kann
JavaScript-Seiten im Browser-Modus rendern.

```python
# async: TextExtraction hat keine blockierende Fassade
from edusharing.extraction import TextExtraction

async with TextExtraction.from_env() as dienst:   # EDU_SHARING_TEXT_EXTRACTION_URL
    ergebnis = await dienst.text_of("https://example.org/artikel")
    print(ergebnis.lang, ergebnis.char_count, ergebnis.text[:200])
```

Für das Schema `repository.<domain>` → `text-extraction.<domain>` lässt sich
der Nachbardienst explizit auswählen. Als Argument funktioniert auch `repo.url`:

```python
# async: TextExtraction hat keine blockierende Fassade
from pathlib import Path

async with TextExtraction.from_repository("https://repository.staging.openeduhub.net") as service:
    result = await service.text_of(
        "https://wirlernenonline.de", method="browser", output_format="markdown",
    )
    if result.text:
        Path("page.md").write_text(result.text, encoding="utf-8")
```

`method="simple", output_format="txt"` liest HTML ohne Browser-Rendering.
Der Browser läuft auf dem Dienst; lokal wird keine Browser-Abhängigkeit benötigt.
Der Konstruktor behält Schema und abweichenden Port bei, entfernt Repository-Pfade
und fragt nicht automatisch die Verfügbarkeit ab. Bei anderem Hostnamen oder
Dienst-Port die Adresse direkt an `TextExtraction(base_url=...)` übergeben oder
`EDU_SHARING_TEXT_EXTRACTION_URL` setzen. `from_env()` benötigt diese Variable
weiterhin. Ein ausführbares URL-zu-Datei-Rezept zeigt
[Beispiel 26](docs/examples/26_extract_page.py).

Der Volltext eines Knotens, aus welcher Quelle auch immer:

```python
# async: der Extraktionsdienst hat keine blockierende Fassade
knoten = await repo.node(node_id)
text = await knoten.content.text()                # was das Repositorium hat
if not text and knoten.get("ccm:wwwurl"):
    geholt = await dienst.text_of(knoten.get("ccm:wwwurl"), max_chars=20_000)
    text = geholt.text                            # geholt.reason sagt warum, falls leer
```

**Kein Text ist ein normales Ergebnis, kein Fehler.** `reason` nennt die
Ursache: `not_http`, `private_host`, `dns_failed` oder `no_text` —
auseinandergehalten, damit „das würden wir nicht abrufen“ nie wie „die Seite
hatte keinen Text“ aussieht.

Am 28.08.2026 gegen den openeduhub-Dienst gemessen (FastAPI, `c766f2e5`):

* **Eine edu-sharing-Download-URL ergibt 424.** Der Dienst kann nicht lesen, was
  das Repositorium selbst hostet — dafür bleibt `node.content.text()`
  zuständig. Wer das nicht weiß, sucht den Fehler bei sich.
* **`status` ist der der Zielseite**, nicht der des Dienstes: eine 200 vom
  Dienst kann eine 404 der Seite tragen.
* **`method="browser"` ist nicht einfach besser.** Auf einer Seite lieferte
  `simple` den Artikel und `browser` den Cookie-Banner. Zwei Versuche, keine
  Rangfolge; liefert der eine nichts, ist der andere dran.

**Es gibt keine Vorgabe-Adresse**, und das mit Absicht: jede Installation
betreibt ihren eigenen Dienst, und eine Vorgabe auf einen Staging-Dienst hat
schon Produktions-Material-URLs in eine fremde Umgebung geschickt. Bei
`from_env()` heißt eine fehlende Dienstvariable weiterhin: kein Client. Die
Ableitung einer Nachbaradresse ist eine eigene, explizite Wahl.

**Die Adresse wählst du, abgerufen wird sie von einem anderen.** Jede Prüfung
läuft, *bevor* etwas gesendet wird: Schema, dann der Host als
IP-Literal-Adresse, dann das, worauf er auflöst — private, Loopback- und
Link-Local-Bereiche werden verweigert, der Wolken-Metadatenendpunkt darunter.
Eine Lücke bleibt und steht im Modul: eine Umleitung passiert im Prozess des
Dienstes, wo diese Bibliothek nicht hinsieht.

### Der Metadata Agent — was in den JSON einer Inhaltsart gehört

`ccm:oeh_extendedType` sagt, *was* eine Ressource ist; `ccm:oeh_extendedData`
trägt daneben einen freien JSON-Bereich. Welche Felder dort hineingehören, steht
in keinem Metadatensatz — das Repositorium speichert den Text und prüft nichts.
Das weiß nur dieser Dienst, und nur zur Laufzeit:

```python
# async: der Agent hat keine blockierende Fassade
from edusharing.metadata_agent import MetadataAgent   # METADATA_AGENT_URL

async with MetadataAgent.from_env() as agent:
    art = await agent.content_type_for(node.get("ccm:oeh_extendedType"))
    schema = await agent.schema(art.schema_file)      # 45 Felder für eine Organisation
```

`content_types()` nennt die acht, die er beschreibt, samt der Vokabular-URI, auf
die jede hört. **Den Dateinamen nicht aus der Inhaltsart ableiten** — gemessen
am 28.08.2026 heißt `profession` dort `occupation.json` und `didactic_concepts`
heißt `didactic_planning_tools.json`. Die maßgebliche Zuordnung steht in
`core.json` selbst, und genau die liest diese Methode.

**Das Repositorium kennt mehr Inhaltsarten als der Agent.** Zehn in `mds_oeh`,
acht hier: `ai_prompt` und `ai_skill` haben kein Schema, `content_type_for`
antwortet dafür mit `None` — kein Fehler, nur ein Knoten, zu dem der Agent
nichts zu sagen hat.

Schemata kommen ungeformt zurück, und das mit Absicht: jedes Feld trägt Label,
Beschreibung, Beispiele **und einen Extraktions-Prompt**, je zweisprachig. Das
in eigene Typen zu gießen hieße, die Struktur eines fremden Dienstes in dieser
Bibliothek einzufrieren.

### Abläufe — ein Anwendungsfall, ein Aufruf

Alles bisher Gezeigte ist nah an edu-sharing und liefert Objekte. Das ist
richtig für Python und unpassend für alles, was das Ergebnis weiterreichen muss.
`repo.flows` erledigt dieselbe Arbeit in einem Aufruf und antwortet in JSON:

```python
ergebnis = repo.flows.search("Photosynthese", subject="Biologie")
json.dumps(ergebnis)                  # geht -- genau darum geht es

angelegt = repo.flows.add_material(   # landet im Home-Verzeichnis
    "Photosynthese einfach erklärt",
    url="https://beispiel.org/m",
    subject="Biologie",               # wird auch schreibend aufgelöst
)
if angelegt["unresolved"]:            # Werte, die NICHT ankamen
    ...
```

Alle Abläufe: `prepare_material`, `place_material`, `collection_context`, `search`, `search_all`, `vocabulary`, `describe`,
`describe_many`, `text`, `related`, `placement`, `relations`,
`child_objects`, `browse_tree`, `search_in_collection`,
`collection_stats`, `find_collections`, `collection_contents`, `page`,
`find_pages`, `find_skills`, `skill`, `skill_registry`, `pick_skill`,
`add_material`, `update_material`, `build_collection`,
`accept_suggestion`, `delete`. Ein- und Ausgabe im Einzelnen in
**[docs/FLOWS.de.md](docs/FLOWS.de.md)**.

`search` nimmt zusätzlich `rerank=True`. edu-sharing UND-verknüpft jedes
Wort, weshalb eine natürlich formulierte Frage nichts findet: gemessen hat
*„Bruchrechnung"* 1591 Datensätze, *„Ich suche ein Arbeitsblatt zur
Bruchrechnung"* **null**. Die Neuordnung fragt mehrere Anfragevarianten und
sortiert nach Relevanz — sie kostet eine Anfrage je Variante und ist aus.

**Nicht alles hat einen Ablauf, und das mit Absicht.** Bewertungen,
Kommentare, das Stellen und das Ablehnen eines Vorschlags, die redaktionelle
Weitergabe, Gruppen, Vorschaubilder und das Umbenennen einer Sammlung
bleiben jeweils bei einer Endpunktfamilie. Das *Annehmen* eines Vorschlags
ist der eine, der daraus erwachsen ist: es schreibt, liest zurück und hakt
erst dann ab — drei Aufrufe, also hat es `accept_suggestion` verdient. Ein Ablauf verdient seinen Platz dadurch, dass er mehrere
zusammenführt — `placement` fragt zwei, `search_all` drei. Eine einzelne
Familie zu umhüllen änderte die Form der Antwort und spart nichts. Diese
Anwendungsfälle stehen oben, auf der API-Ebene.

Ausprobieren: `python docs/examples/05_flow_search.py`, `06_flow_create.py`,
`07_flow_collection.py`, `08_flow_rerank.py`, `09_flow_browse.py`

## Wohin es geht

Ein MCP-Server als dünner Adapter über `edusharing.agent` — die Bausteine dafür
stehen, der Server selbst ist bewusst nicht Teil der Bibliothek.

## Was die Bibliothek für dich weiß

Ein paar Verhaltensweisen von edu-sharing kann man nicht raten. Sie sind hier
eincodiert statt dokumentiert:

- **Ein Bearer-Token wird abgelehnt, nicht gesendet.** edu-sharing kennt nur
  Basic-Auth und Session-Cookies — und *ignoriert* einen Bearer-Header, statt
  ihn abzulehnen. Die Anfrage liefe unbemerkt als Gast.
- **HTTP 500 heißt manchmal „nicht angemeldet".** Ein Gast auf einem
  geschützten Endpunkt bekommt 500 mit „Not allowed for guest user". Das wird
  zu `AuthenticationError` — und nicht wiederholt.
- **Das Passwort geht nur an das konfigurierte Repositorium.** Auch dann, wenn
  eine URL aus Antwortdaten woandershin zeigt.
- **Ein Vokabular zu haben heißt nicht, danach filtern zu können.**
  `ccm:taxonid` führt in beiden geprüften Metadatensätzen ein Vokabular, ist aber
  nur in `mds_oeh` filterbar. Trifft die Suche darauf, ergänzt die Bibliothek die
  Servermeldung um den fehlenden Hinweis.
- **`pattern:""` listet alle Vokabularwerte** — das naheliegende `"-all-"` gibt
  lautlos eine leere Liste zurück.
- **Nicht auflösbare Filter werden gemeldet, nicht verworfen.** Eine
  fallengelassene Einschränkung liefert Treffer, die niemand angefragt hat, und
  sieht dabei wie ein Ergebnis aus.
- **`200 OK` ist kein Persistenzbeweis** beim Schreiben — siehe oben.
- **`downloadUrl` belegt nicht, dass es eine Datei gibt.** Sie ist immer gesetzt;
  ein Knoten ohne Inhalt liefert daran 200 mit null Bytes. `content.has_content`
  prüft den Hash, der auch eine 0-Byte-Datei von *gar keiner* Datei unterscheidet.
- **Schlagworte sind eine geteilte Liste.** `add_keywords` ergänzt; wer
  `cclom:general_keyword` direkt setzt, löscht fremde Einträge.
- **Was eine Anwendung anlegt, sieht sonst niemand.** Auch nicht nach dem
  Einhängen in eine öffentliche Sammlung, auch nicht mit `scope="PUBLIC"` —
  siehe unten.
- **Ein Recht zu setzen würde die übrigen löschen.** Der `POST` des
  Repositoriums ersetzt die ganze lokale Rechteliste; `grant()` führt zusammen.
- **Eine Bewertung von `0` ist eine Stimme, kein Zurücksetzen.** Sie senkt den
  Schnitt; entfernt wird mit `unrate()`.
- **Ein Kommentartext wird Byte für Byte abgelegt.** Als JSON gesendet landen
  die Anführungszeichen mit im Text.

### Veröffentlichen — der Schritt, den edu-sharing nicht tut

Material, das eine Anwendung anlegt, kann ihr Urheber lesen und **sonst
niemand**. Es in eine öffentliche Sammlung zu hängen ändert daran nichts, und
`scope="PUBLIC"` an der Sammlung auch nicht — beides am 28.08.2026 gemessen,
beides mit `200` auf dem Weg.

```python
node = repo.create_node(ordner.id, name="material.txt", title="Photosynthese")
node.is_public                       # False — kostenlos, die Antwort trägt es
node.permissions.publish()           # True: jetzt veröffentlicht
node.permissions.publish()           # False: war es schon
```

`publish()` führt zusammen. Der `POST` des Repositoriums **ersetzt** die ganze
lokale Rechteliste — wer ohne Zusammenführen veröffentlicht, nimmt allen
anderen unbemerkt ihre Rechte, mit einem `200` davor.

```python
node.permissions.grant("GROUP_lehrer", "Coordinator")
node.permissions.revoke("GROUP_lehrer")
rechte = node.permissions.get()
rechte.is_public                     # geerbter Zugriff zählt mit
rechte.allows("alice", "Consumer")
```

Ein Knoten in einem öffentlichen Ordner ist ohne eigenen Eintrag öffentlich.
`unpublish()` sagt das, statt eine Vertraulichkeit zu melden, die es nicht gibt:

```python
node.permissions.unpublish()         # ConflictError: über das Elternteil öffentlich
```

In den Abläufen steht dieselbe Frage. `public` steht in jeder Antwort, und der
Schalter ist aus, weil Gelesenes sich nicht zurücknehmen lässt:

```python
repo.flows.add_material("Photosynthese", publish=True)["public"]   # True
```

### Wenn ein Schreibvorgang halb glückt

edu-sharing antwortet mit HTTP 200 auch auf Schreibvorgänge, die es nicht
vollständig speichert. Die Bibliothek liest Eigenschafts-Schreibvorgänge
zurück — `update`, `set_property` und das Anlegen eines Knotens gleichermaßen —
und wirft einen `SilentDropError`, der die nicht
angekommenen Eigenschaften benennt.

Drei gemessene Ursachen:

| Ursache | Beispiel | Was hilft |
|---|---|---|
| Nicht im Metadatensatz | `ccm:oeh_collection_compendium_text` | `set_property()` schreibt daran vorbei |
| Vom Repositorium abgeleitet | `ccm:oeh_lrt_aggregated` aus `ccm:oeh_lrt` | das Quellfeld schreiben |
| Regel des Knotentyps | `cm:title` an einem neuen `cm:folder` | nachträglich per `update()` setzen |

`create(verify=False)` schaltet die Prüfung ab, wenn ein abgeleitetes Feld
bewusst mitgeschickt wird.

**Und einer, der mit dem richtigen Status und der falschen Bedeutung
ankommt.** Am 28.08.2026 mit gültiger Anmeldung gemessen: 20 Knoten je Runde,
5 Runden — nacheinander gesendet antworteten `0 von 100` Anfragen mit `401`,
gleichzeitig gesendet `9 von 100`. Dieselben Knoten, dieselben Zugangsdaten.
Der Transport wiederholt einen `401` deshalb **einmal**, wenn die Verbindung
angemeldet ist, und gar nicht, wenn sie anonym ist (dort heißt er „dafür
braucht es eine Anmeldung“ und heißt es beim zweiten Mal wieder). Einmal, nicht
`max_retries` mal — ein zusätzlicher Versuch ist der Preis für den gemessenen
Ausrutscher, drei wären eine Strafe für einen Tippfehler im Passwort.

**Und was schon geschehen sein könnte, wird nicht noch einmal gesendet.** Nach
einem Timeout nach dem Senden oder einem `5xx` weiß niemand, ob das
Repositorium die Anfrage ausgeführt hat. Der Transport sendet dann nur erneut,
was zweimal ankommen darf: Lesezugriffe und die Schreibvorgänge, die bloß einen
Zustand setzen — `update`, `set_property`, Rechte, Bewertungen,
`collections.update`, der Text eines Kommentars, das Vorschaubild. Anlegen,
Löschen, in eine Sammlung legen werfen stattdessen `TransportError` mit dem
Hinweis, dass die Anfrage ausgeführt worden sein könnte — nachsehen, dann
entscheiden. Ein Verbindungsfehler von vor dem Senden wird für jede Methode
wiederholt. Auf einer Instanz, die ihre Fehlermeldungen zurückhält, trägt ein
`5xx` bei einem Schreibvorgang eine Notiz: es kann der gemessene
Login-Ausrutscher sein, kein Serverfehler — zurücklesen, dann entscheiden.

**Der `429` ist die Ausnahme von dieser Regel.** Er sagt, dass die Anfrage
abgewiesen und nicht ausgeführt wurde — also darf auch ein Schreibvorgang
erneut gehen. Er kommt als `RateLimitedError` an, und `retry_after` trägt die
vom Dienst genannten Sekunden: kurze Wartezeiten werden für dich abgewartet,
eine lange kommt mit der Zahl bei dir an, denn eine Stunde in einem Aufruf zu
schlafen ist keine Wiederholung, sondern ein Aufhänger. Die Pause zwischen
zwei Versuchen streut, damit acht Aufrufe einer Fan-out-Welle nicht in
derselben Millisekunde zurückkommen.

Dazu drei Fehler, die mit dem falschen Status ankommen — damit `except
NotFoundError` sie wirklich fängt, und damit der Transport nicht dreimal
wiederholt, was nie gelingen kann:

| Kommt als | Ist wirklich | Wo |
|---|---|---|
| `500 Not allowed for guest user` | nicht angemeldet | jeder geschützte Endpunkt |
| `500 UsageException: Node does not exist` | `404` | `/usage/v1/…/collections` |
| `500 AccessDeniedException` | `403` | `…/parents` an fremdem Material |
| `500 NotAnAdminException` | `403` | `/rating/…/history`, Gruppenmitglieder |

### Bewertungen und Kommentare

Was eine Gemeinschaft an einem Knoten hinterlässt. Eine Bewertung zu lesen
kostet nichts — die Knotenantwort trägt die Zusammenfassung mit, wie `isPublic`:

```python
node = repo.node("abc-123")
node.rating                          # Rating(4.0 aus 3) oder None
node.rate(4, "Sehr brauchbar")       # schreibt, liest den neuen Schnitt zurück
node.unrate()                        # nimmt die eigene Stimme zurück
```

> **Eine Bewertung von `0` wird abgelehnt.** Gemessen am 28.08.2026: sie nimmt
> *nichts* zurück — danach steht am Knoten `count: 1, rating: 0.0`, die Null
> zählt also als abgegebene Stimme und zieht den Schnitt herunter.
> Zurückgenommen wird mit `unrate()`.

```python
node.comments.list()                 # [Comment('alice': 'Sehr brauchbar')]
c = node.comments.add("Erster")
node.comments.add("Antwort", reply_to=c.id)
node.comments.edit(c.id, "Nachgebessert")
node.comments.delete(c.id)
```

> **Der Kommentartext wird 1:1 gespeichert.** edu-sharing wertet den Body hier
> nicht als JSON aus — über `json=` gesendet stünde `"Erster"` im Text, mit
> Anführungszeichen. Die Bibliothek schickt rohe UTF-8-Bytes mit dem
> Content-Type `application/json`, den der Endpunkt verlangt. Geändert wird per
> `POST` am Kommentar; ein `PUT` dort legt einen Kommentar *am Kommentar* an
> und antwortet 500.

### Vorschlagen statt schreiben, und zur Prüfung weiterreichen

Zwei Schritte, die eine Maschine tun sollte, *statt* zu schreiben: einen Wert
zur Abwägung vorschlagen, und einen Datensatz in eine Redaktions-Warteschlange
legen.

```python
node = repo.node("abc-123")
v = node.suggestions.propose("ccm:taxonid", uri, "Der Titel nennt Zellen", confidence=0.9)
node.suggestions.list()              # [Suggestion('ccm:taxonid'='…', PENDING)]
node.suggestions.decide([v.id])      # ACCEPTED — siehe den Vorbehalt
node.suggestions.decide([v.id], accept=False)
```

> **Annehmen trägt den Wert nicht ein.** Gemessen am 28.08.2026, und vom
> `wlo-mcp-sc` davor: nach `ACCEPTED` waren die Schlagworte des Knotens
> weiterhin leer. `/suggestions/v1` ist ein Ablagefach mit Protokoll — wer was
> vorgeschlagen, wer was entschieden hat. Den Wert an den Knoten zu schreiben
> bleibt ein eigener, bewusster Schritt.
>
> Die IDs gehören außerdem in den **Query**, nicht in den Body. Als Body
> gesendet werden sie ignoriert, und jeder Vorschlag bleibt `PENDING` — mit
> einem 200 davor, weshalb `decide()` die Stände zurückliest.

```python
node.workflow.submit("GROUP_redaktion", "100_tocheck", "Bitte prüfen")
node.workflow.history()              # neueste zuerst
```

`status` hat keine Vorgabe: das Vokabular gehört der Instanz (WLO nutzt
`100_tocheck`), und Raten legte Material in eine Warteschlange, die es nicht
gibt.

### Vorschaubilder, Blättern, Sammlung umbenennen

```python
node.preview_url                     # None, wenn es nur ein Typ-Symbol ist
node.content.set_preview(png_bytes)  # Multipart-Feld "image", nicht "file"
node.content.delete_preview()

seite = repo.nodes.children(ordner_id, limit=50, offset=0, only="files")
seite.nodes, seite.total, seite.offset

repo.collections.update(sammlung_id, title="Neu", description="…")
```

> **Eine Vorschau-Adresse steht immer da** — auch ohne Bild und sogar nach dem
> Löschen. Das Repositorium liefert darunter ein Typ-Symbol. `isIcon`
> unterscheidet, weshalb `preview_url` lieber `None` gibt als eine Adresse, die
> ein Allerweltssymbol zeigt. Dieselbe Falle wie bei `downloadUrl`.

> **`repo.nodes.children()` ist nicht `node.children`.** Das erste ist die
> schlichte Auflistung, geblättert und sortiert; das zweite gibt die
> *Serienobjekte* — die Dokumente, die zu einem Material gehören. Das Blättern
> hat eine Sortier-Vorgabe, weil Blättern über eine ungeordnete Liste Einträge
> doppelt bringt und andere ausläßt.

> **Umbenennen braucht `ref.id` im Body**, obwohl die ID im Pfad steht — ohne
> sie: `500 NullPointerException`. Es braucht außerdem einen `title`, weshalb
> das Ändern nur der Beschreibung den bestehenden erst liest. Und die
> Beschreibung gehört *in* das `collection`-Objekt: als
> `properties["cm:description"]` wird sie still verworfen. Ein neuer Titel
> ändert auch `cm:name`.

### Gruppen — wer moderieren darf

```python
for gruppe in repo.people.memberships():
    print(gruppe.name, gruppe.display_name, gruppe.type)   # GROUP_ORG_… · AI-Compliance · EDITORIAL

repo.people.group("GROUP_ORG_AI-Skills")
repo.people.members("GROUP_ORG_AI-Skills")   # [Member('alice'), Member('GROUP_x', Gruppe)]
```

`Member.is_group` ist wichtig: eine Gruppe kann Gruppen enthalten, und eine
verschachtelte als Person zu behandeln beantwortet „wer darf moderieren" falsch.

> **Mitglieder zu lesen braucht Verwaltungsrechte, nicht Mitgliedschaft.**
> Gemessen: für eine Gruppe, in der man nur Mitglied ist, antwortet der
> Endpunkt `500 AccessDeniedException`. Die Bibliothek übersetzt das zu
> `PermissionDeniedError` — als Serverfehler würde der Transport es dreimal
> wiederholen.
>
> Außerdem steht `maxItems` dort still auf **10**: eine Gruppe mit fünfzig
> Mitgliedern käme als Gruppe mit zehn zurück. Die Bibliothek fragt hundert an.

```python
repo.people.create_group("GROUP_projekt", display_name="Projekt")
repo.people.add_member("GROUP_projekt", "alice")
repo.people.remove_member("GROUP_projekt", "alice")
repo.people.delete_group("GROUP_projekt")
```

> **Diese vier sind nicht gegen eine laufende Instanz verifiziert.** Das
> Testkonto antwortet auf `POST /iam/v1/groups/…` mit 403 — belegt ist damit
> nur die Anfrageform: Methode, Pfad, Body, gegen das OpenAPI-Modell. Dass ein
> Repositorium sie annimmt, ist unbelegt, und die Docstrings sagen es noch
> einmal.

### Wo ein Knoten liegt — und wer ihn kuratiert hat

Zwei Fragen, die sich ähneln und es nicht sind. Eine Sammlung hält eine
*Referenz*: der Knoten, auf den sie zeigt, hat sein Elternteil ganz woanders.
Ein Knoten in zehn Sammlungen hat trotzdem genau eine Elternkette.

```python
node = repo.node("abc-123")
[o.title for o in node.parents()]      # der nächste zuerst — wo er liegt
[s.title for s in node.collections()]  # wer ihn kuratiert hat
```

Oder beides in einem Aufruf, mit dem Pfad zum Anzeigen umgedreht:

```python
repo.flows.placement("abc-123")
# {"title": "…", "path": [oben, …, nächster], "collections": [...], "scope": "MY_FILES"}
```

`scope` sagt, wie weit der Pfad reicht. Er endet an der Grenze dessen, was das
Konto lesen darf — den vollständigen Pfad zu verlangen endet für ein
gewöhnliches Konto mit **403**, gemessen. Ein abgeschnittener Pfad wird also als
solcher gemeldet, statt als vollständiger durchzugehen.

### Serienobjekte — Dokumente, die zu einem Material gehören

Ein Lösungsblatt, ein Handout, ein zweites Dateiformat: edu-sharing führt die
unter dem Hauptknoten, nicht daneben.

```python
node = repo.node(node_id)
node.children.add(pdf, filename="loesung.pdf", mimetype="application/pdf")
repo.flows.child_objects(node_id)
```

Die drei Parameter, die eines anlegen, sind nicht zu erraten —
`ccm:io_childobject` ist ein Aspekt, kein Typ, und ohne
`assocType=ccm:childio` antwortet das Repositorium mit HTTP 500. Einzelheiten in
[docs/FLOWS.de.md](docs/FLOWS.de.md).

### Relationen — Knoten, die zusammengehören

Eine Reihe und ihre Folgen, ein Arbeitsblatt und das Video, auf dem es aufbaut:
edu-sharing führt das als **Relationen** zwischen Knoten, die nebeneinander
stehen — getrennt von Sammlungen.

```python
repo.relations.create(teil_id, "isPartOf", reihe_id)
repo.flows.relations(node_id=reihe_id)      # die Reihe meldet "hasPart"
```

Die Gegenrichtung wird automatisch geführt. Die API unterscheidet zudem
maschinell vorgeschlagene von bestätigten Verknüpfungen (`ai_generated`,
`approve`) — was zählt, wenn ein Modell die Vorschläge macht.

**Das Argument `metadata` überlebt nicht.** edu-sharing 11.0 nimmt es mit
HTTP 200 an und speichert nichts — gemessen am 28.08.2026 in drei Formen, die
letzte direkt am Endpunkt, jedes Mal kam `metadata: {}` zurück. `create()` liest
es deshalb zurück und wirft `SilentDropError`; die Verknüpfung selbst entsteht.
Die Begründung gehört an die Knoten oder in den eigenen Speicher. Einzelheiten in
[docs/FLOWS.de.md](docs/FLOWS.de.md#relations--womit-ein-knoten-verknüpft-ist).

### Kuratierte Seiten — was eine Sammlung rendert

Der Page Builder von edu-sharing: eine Sammlung kann eine Startseite tragen,
aufgebaut aus *Schwimmlinien*, jede mit Widgets, jedes Widget auf einen Knoten
zeigend. WirLernenOnline nennt das „Themenseite“, aber daran ist nichts von WLO
— die Eigenschaften gehören zum Inhaltsmodell von edu-sharing, und jede
Instanz, die den Page Builder benutzt, speichert sie gleich.

```python
node = repo.node(node_id=collection_id)
page = node.page.get()              # None, wenn die Sammlung keine hat
if page:
    print(page.rendered.title, len(page.rendered.swimlanes))
    node.page.render(andere_variante)   # sofort öffentlich sichtbar
```

Oder als Ablauf, JSON-fertig:

```python
repo.flows.find_pages("Deutsch")    # welche Sammlungen eine tragen
repo.flows.page(collection_id, resolve_widgets=True)
```

Drei Dinge, die man vorher wissen sollte, alle am 28.08.2026 gemessen:

* Ein Seitendokument **ohne** `default` rendert die *erste* Variante seiner
  Liste. `by_position` hält die beiden Zustände auseinander — für den Besucher
  sehen sie gleich aus, für einen Schreibvorgang sind sie es nicht.
* **Eine Seite zu haben ist nicht, Inhalt zu haben.** Eine gemessene Sammlung
  trägt eine Seite, deren einzige Variante null Schwimmlinien konfiguriert.
* **An diesen Dokumenten validiert nichts.** Die Property-Route speichert die
  Zeichenkette `"not json at all"` mit einer `200`. Darum wirft das Lesen an
  einem kaputten Dokument nie (`readable` sagt es), und `render()` verweigert
  alles, was es nicht belegen kann — es redigiert das gespeicherte Dokument,
  statt ein neues zu komponieren.

Im Einzelnen in
[docs/FLOWS.de.md](docs/FLOWS.de.md#page--die-kuratierte-seite-die-eine-sammlung-rendert).

### Was diese Bibliothek nicht tut

* **Wikipedia zusammenfassen.** Kein edu-sharing. Der volle Artikeltext ist
  über den Extraktionsdienst erreichbar wie jede andere Seite; ein Client für
  die Wikipedia-API ist das Paket von jemand anderem.
* **Eine URL selbst abrufen.** Das Abrufen macht der Extraktionsdienst, in
  seinem eigenen Prozess. Diese Bibliothek schickt ihm eine Adresse — und
  prüft sie vorher.
* **Dokumentkonventionen einzelner Repositorien parsen.** Ein Dokument zu
  finden ist generisch und steht unten unter *Felder und Dateien*; was sein
  Markdown bedeutet, ist die Konvention derer, die es geschrieben haben.
* **Varianten anlegen, löschen, umsortieren oder Schwimmlinien bearbeiten.**
  Nur, welche Variante rendert. Ein kaputtes Seitendokument fällt nicht beim
  Schreiben auf, sondern später, im Page Builder, auf einer Seite, die das
  Publikum liest.

## Felder und Dateien, die keine Kurznamen haben

Die Kurznamen (`subject`, `level`, …) sind eine Bequemlichkeit für die Handvoll
Eigenschaften, nach denen gefiltert wird. Alles andere ist ebenso erreichbar —
die Bibliothek schränkt nicht ein, was ein Knoten tragen darf.

**Beliebige Eigenschaften, lesend und schreibend:**

```python
node = repo.node(node_id)
node.get("ccm:oeh_collection_compendium_text")       # eine lesen
node.get_all("ccm:taxonid")                          # alle Werte
node.properties                                      # alles auf einmal

node.update(properties={"ccm:custom": ["x"]})  # schreiben, mit Prüfung
node.set_property("ccm:custom", "x")           # schreiben, am mds vorbei
```

`update()` wird gegen den Metadatensatz geprüft und wirft einen
`SilentDropError`, wenn edu-sharing einen Schreibvorgang annimmt und nicht
speichert. Eine Eigenschaft, die der Metadatensatz nicht vorsieht — der
WLO-Kompendialtext ist eine davon — muss über `set_property()` gehen, das direkt
schreibt. Gemessen am 27.08.2026: `ccm:oeh_collection_compendium_text` wird von
`update()` unter `mds_oeh` verworfen und von `set_property()` gespeichert.

**Ein freier JSON-Bereich ist auch nur eine Property.** Manche Instanzen führen
eine Inhaltsart plus einen offenen Datenbereich — WLO nennt sie
`ccm:oeh_extendedType` (ein Vokabular: KI-Prompt, Organisation, Person,
Veranstaltung, …) und `ccm:oeh_extendedData` (Freitext). Nichts in dieser
Bibliothek kennt sie, und nichts muss das:

```python
uri = repo.vocab.resolve("ccm:oeh_extendedType", "KI-Prompt")  # URI dieser Instanz
node.update(properties={
    "ccm:oeh_extendedType": [uri],
    "ccm:oeh_extendedData": [json.dumps({"modell": "gpt-5", "temperatur": 0.2})],
})
repo.search("", filters={"ccm:oeh_extendedType": "KI-Prompt"})  # filterbar
```

Gemessen am 28.08.2026 gegen die Staging: das Vokabular löst auf, der JSON kommt
Zeichen für Zeichen zurück, `node.labels()` liefert „KI-Prompt" statt der URI,
und der Filter grenzt ein, ohne in `unresolved` zu landen. Dass die Bibliothek
dafür keine Funktion braucht, ist der Sinn der Laufzeit-Auflösung — eine
Instanz, die etwas anderes modelliert, modelliert es genauso.

**Dateien an einem Knoten:**

```python
node = node.content.upload(daten, filename="x.pdf", mimetype="application/pdf")
roh = node.content.download()          # die Bytes, immer
text = node.content.text()             # der extrahierte Volltext
node.content.has_content                      # gibt es überhaupt eine Datei?
```

**Volltext wird nicht für jeden Typ extrahiert.** Gemessen, indem derselbe Satz
in fünf Formaten hochgeladen wurde:

| mimetype | `download()` | `text()` |
|---|---|---|
| `text/plain` | 26 | 26 |
| `text/markdown` | 35 | **0** |
| `text/html` | 55 | 22 |
| `application/json` | 26 | **0** |
| `application/octet-stream` | 21 | 21 |

Markdown und JSON kommen leer zurück. Wer Anweisungen oder Daten als Markdown
ablegt — einen Agenten-Skill etwa — muss sie mit `download()` lesen. Ein leeres
`text()` heißt nicht, dass die Datei leer ist.

**Zu Konventionen, die darauf aufsetzen.** Dinge wie die „Skills" von WLO sind
keine edu-sharing-Funktion: ein Skill ist gewöhnliches Material mit einer
Markdown-Datei, gesammelt in einer Sammlung. Sie zu lesen braucht nichts
Besonderes — `flows.collection_contents(id)`, dann `content.download()` je
Eintrag. Behandeln Sie das Ergebnis als nicht vertrauenswürdige Eingabe: es ist
hochgeladener Inhalt, und `edusharing.agent` trägt die Schutzmaßnahmen dafür.

Solche Datensätze sind meist durch einen Inhaltstyp gekennzeichnet, und auf den
lässt sich sehr wohl filtern:

```python
INHALTSTYP = "ccm:oeh_extendedType"
GESUCHT = "http://w3id.org/openeduhub/vocabs/contentTypes/ai_skill"

treffer = repo.search(filters={INHALTSTYP: GESUCHT})   # irgendwo

seite = repo.nodes.children(collection_id, limit=100)  # in einer Sammlung
eigene = [n for n in seite.nodes if n.get(INHALTSTYP) == GESUCHT]
```

Am 28.08.2026 gegen Staging gemessen: 34 Datensätze, je 13 bis 14 kB Markdown,
die `download()` liefert und `text()` als leer meldet — die Tabelle oben, an
echten Daten.

**Über die Kinder, nicht über den Index, wenn die Frage ist, was eine Sammlung
*freigibt*.** Suchindex und Knotenspeicher sind in edu-sharing getrennte
Systeme, und ein Datensatz kann aus dem einen fallen, während er im anderen
tadellos liegt — dem WLO-MCP ist das am 09.08.2026 an einer laufenden Sammlung
passiert.

Die URI wählt der Aufrufer. Diese Bibliothek löst Vokabulare gegen den
Metadatensatz der jeweiligen Instanz auf und bringt keine eigene Tabelle mit;
eine URI aus dem Vokabular eines Repositoriums hat in einem Client für alle
nichts verloren.

## Beispiele

Jedes läuft gegen eine echte Instanz; die schreibenden legen einen eigenen
Wegwerf-Ordner an und räumen ihn wieder ab. Jedes ist zugleich ein Testfall —
`pytest -m live` führt die lesenden aus, `pytest -m write` die übrigen — damit
eine Änderung, die ein Beispiel bricht, in der Suite auffällt und nicht erst
beim Nächsten, der es ausprobiert.

**Direkt gegen die API** — es kommen Objekte zurück, mit denen weitergearbeitet
wird:

| | |
|---|---|
| [`01_connect.py`](docs/examples/01_connect.py) | verbinden, sehen wer man ist und was die Instanz kann |
| [`02_search.py`](docs/examples/02_search.py) | suchen mit Filtern und Facetten, Vokabular auflösen |
| [`03_write.py`](docs/examples/03_write.py) | anlegen, ändern, prüfen — und wie ein stiller Verlust aussieht |
| [`04_agent_blocks.py`](docs/examples/04_agent_blocks.py) | die Bausteine für KI-Nutzung: Sicherheit, Bereinigung, Formatierung |
| [`11_publish.py`](docs/examples/11_publish.py) | Material für andere sichtbar machen — der Schritt, den nichts von allein tut |
| [`15_full_text.py`](docs/examples/15_full_text.py) | der Volltext eines Materials, aus dem Repositorium oder vom Extraktionsdienst |
| [`26_extract_page.py`](docs/examples/26_extract_page.py) | eine Webseite als Text/Markdown oder UTF-8-Datei; explizite oder vom Repository abgeleitete Dienstadresse |
| [`16_editorial.py`](docs/examples/16_editorial.py) | kommentieren, bewerten, vorschlagen, zur Prüfung geben — die redaktionellen Flächen auf der API-Ebene |

**Über Abläufe** — es kommt ein `dict` zurück, fertig zum Weiterreichen:

| | |
|---|---|
| [`05_flow_search.py`](docs/examples/05_flow_search.py) | Vokabular erfragen, suchen, einen Treffer beschreiben |
| [`06_flow_create.py`](docs/examples/06_flow_create.py) | anlegen mit Vokabular — und was ein unbekannter Wert bewirkt |
| [`07_flow_collection.py`](docs/examples/07_flow_collection.py) | Sammlung anlegen, füllen, Teilerfolg beobachten |
| [`08_flow_rerank.py`](docs/examples/08_flow_rerank.py) | was ein Rahmenwort kostet und was `rerank=True` zurückholt |
| [`09_flow_browse.py`](docs/examples/09_flow_browse.py) | Sammlungen finden, öffnen, Inhalt ändern |
| [`12_flow_place.py`](docs/examples/12_flow_place.py) | eine Anfrage für Material und Sammlungen, dann wo ein Treffer liegt |
| [`13_flow_tree.py`](docs/examples/13_flow_tree.py) | eine Sammlung ablaufen, darin suchen, sie auszählen |
| [`14_flow_page.py`](docs/examples/14_flow_page.py) | die kuratierte Seite einer Sammlung lesen, samt Widgets — und dieselbe Seite als Objekte |
| [`17_flow_belonging.py`](docs/examples/17_flow_belonging.py) | die drei Arten von Zugehörigkeit: Sammlung, Serienobjekt, Beziehung |
| [`18_video_recommendation.py`](docs/examples/18_video_recommendation.py) | zehn Videos zu einem Thema, umsortiert, dann empfiehlt ein Modell eines |
| [`19_collection_audit.py`](docs/examples/19_collection_audit.py) | eine Sammlung prüfen — und warum ein leerer `path` nicht „nirgends“ heißt |
| [`20_provider_load.py`](docs/examples/20_provider_load.py) | welches Modell antworten soll, und woran man das misst - Auslastung, Verbünde, Verweigerung |
| [`21_skills.py`](docs/examples/21_skills.py) | welche Skills eine Sammlung freigibt, und was einer davon sagt |
| [`22_bapi_templates.py`](docs/examples/22_bapi_templates.py) | ein Prompt, der auf dem Server liegt, gefüllt aus einer Sammlung — und was freier Text mit ihm macht |
| [`23_ai_suggestions.py`](docs/examples/23_ai_suggestions.py) | das Modell schlägt Schlagworte vor, ein Programm übernimmt das beste — und liest es zurück |
| [`24_generic_metadata.py`](docs/examples/24_generic_metadata.py) | MDS, eigenes Profil, Vokabulare und Snapshots |
| [`25_prepare_context.py`](docs/examples/25_prepare_context.py) | Materialentwurf und Sammlungskontext, rein lesend |

**Beide Ebenen nebeneinander:**

| | |
|---|---|
| [`10_two_levels.py`](docs/examples/10_two_levels.py) | derselbe Anwendungsfall zweimal geschrieben, mit Zählung der Anfragen |

Fangen Sie mit `10_two_levels.py` an, wenn Sie entscheiden, gegen welche Ebene
Sie schreiben. Es zeigt, dass `search` und `add_material` in beiden Fassungen
exakt dieselben Anfragen schicken — der Ablauf ändert die Ausgabeform, nicht die
Arbeit — und wo ein Ablauf wirklich einen Umlauf spart.

## Aufbau

| Schicht | Inhalt |
|---|---|
| `edusharing.agent` | Bausteine für KI-Anwendungen: Formatierung, Token-Budget, Preview-then-confirm, Sanitisierung |
| `edusharing.flows` | ein Anwendungsfall, ein Aufruf, ein `dict` zurück |
| `edusharing` (Ressourcen) | `search()`, `node()`, `find_collections()` — Objekte zurück |
| Profil & MDS | Vokabular-Auflösung, Property-Fähigkeiten, Wahl des Schreibwegs |
| Transport | httpx, Auth, Retry, Concurrency, Rückleseprobe |
| `_generated` | alle 389 Operationen, aus `openapi.json` erzeugt |

Daneben, nicht darin — drei Dienste mit eigener Adresse, eigenständig gebaut,
weil eine Verbindung zum Repositorium nichts darüber sagt, ob es sie gibt:

| Modul | Dienst |
|---|---|
| `edusharing.bapi` | das LLM-Gateway (`B_API_BASE_URL` + `B_API_KEY`): der Proxy `BildungsAPI` und der Template-Modus `BapiTemplates` |
| `edusharing.extraction` | der Volltextdienst (`EDU_SHARING_TEXT_EXTRACTION_URL`) |
| `edusharing.metadata_agent` | der Metadata Agent: welche Felder eine Inhaltsart trägt (`METADATA_AGENT_URL`) |

## Generierte Schicht neu bauen

```bash
python scripts/generate_client.py
```

Das baut aus der Referenz-Spec unter `openapi/` — damit anfangen, dann zeigt der
Diff, was der Generator getan hat, und sonst nichts. Erst danach, um eine neuere
Instanz aufzunehmen:

```bash
python scripts/generate_client.py --from-instance https://repository.staging.openeduhub.net
```

Das Script normalisiert die Spec zuerst — ohne diesen Schritt erzeugt der
Generator ungültiges Python; die Begründung steht in seinem Docstring. Es ruft
den Generator aus `uv.lock` auf, nicht die neueste Fassung von PyPI, und
schreibt `src/edusharing/_generated/GENERATED.md` mit Generator-Fassung und
SHA-256 der Spec, damit ein späterer Diff als Spec-Änderung *oder*
Generator-Änderung lesbar ist (Audit DEP-2). Aus dem Projektverzeichnis
starten: dort liest der Generator `requires-python` und die Zeilenbreite aus
`pyproject.toml` — außerhalb ergeben derselbe Generator und dieselbe Spec 556
anders geformte Dateien.

## Protokoll

Bei `INFO` und `DEBUG` schweigt die Bibliothek standardmäßig, wie eine
Bibliothek es soll. Ein Dienst schaltet sie ein, wo er sie braucht:

```python
import logging

logging.getLogger("edusharing").setLevel(logging.INFO)   # Wiederholungen, Modellwechsel
logging.getLogger("edusharing").setLevel(logging.DEBUG)  # zusätzlich jede Anfrage
```

`INFO` meldet, worüber man sonst im Nachhinein rätselt: eine Wiederholung, und
welches b-api-Modell geantwortet hat, nachdem ein früherer Kandidat abgelehnt
hatte. `DEBUG` ergänzt Methode und URL jeder Anfrage.

`WARNING` ist die Ausnahme vom Schweigen, und das mit Absicht: Python gibt sie
auch ohne konfiguriertes Protokoll auf stderr aus. Jede benennt etwas, das der
Aufrufer sonst nie erführe:

| Wo | Was sie sagt |
|---|---|
| `extraction.py` | Der Extraktionsdienst hat eine Adresse verweigert — eine private, eine, die sich nicht auflösen ließ, eine, die in einen privaten Bereich auflöste, oder eine, die zwei Parser verschieden lesen |
| `childobjects.py` | Ein Kindknoten wurde angelegt, dann aber weder gefüllt noch entfernt. Er bleibt leer stehen, und der Fehler, den der Aufrufer bekommt, handelt vom Hochladen und weiß nichts von ihm |
| `bapi/choice.py` | Die **Bibliothek** hat ein Modell gewählt, das der Anbieter zurückgezogen hat. Es antwortet weiter, also wird es nicht ausgeschlossen — aber niemand sonst kann bemerken, dass die Wahl nicht die des Aufrufers war |
| `_sync.py` | Die Hintergrundschleife hielt nicht rechtzeitig an. Sie bleibt offen, statt dass darüber geworfen wird, und das ist ein Leck, das eine Zeile wert ist |

Eine Anzahl steht hier nicht mehr. Es hieß „an vier Stellen", als es fünf
waren, und sieben, als jemand wieder nachzählte (Audit DOC-7);
`tests/test_docs_inventories.py` schlägt jetzt an, wenn ein Modul warnt, ohne
oben genannt zu sein.

Header werden nie protokolliert. Dort stehen die Zugangsdaten, und eine
Protokollzeile wird aggregiert, durchsucht und aufbewahrt.

## Tests

```bash
uv run pytest
```

Läuft offline und deterministisch. Tests gegen eine echte Instanz sind separat:

```bash
EDU_SHARING_URL=https://repository.staging.openeduhub.net uv run pytest -m live
```

Schreibtests (`-m write`) brauchen Zugangsdaten und arbeiten ausschließlich in
einem Wegwerf-Ordner, den sie selbst anlegen. Zugangsdaten allein genügen
nicht: das Konto braucht zusätzlich die Toolpermission
`TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS`. Gemessen am 21.09.2026 gegen die
Staging mit einem Konto, das Material und Sammlungen anlegen darf und Ordner
nicht: von 90 schreibmarkierten Tests sind **9 grün und 81 nicht** — 72 enden
in der Ordner-Fixture an `HTTP 403 DAOToolPermissionException`, bevor
irgendetwas geschrieben wird, und 9 sind die schreibenden Beispiele, die im
eigenen Prozess genauso scheitern. Die neun Grünen bauen sich eine
Wegwerf-**Sammlung** statt eines Ordners; die Toolpermission kostet also alles,
was einen Ordner braucht, und sonst nichts.

Die Suiten gegen die drei Nachbardienste überspringen sich still ohne ihre
eigenen Variablen — `B_API_KEY` **und** `B_API_BASE_URL` für das LLM-Gateway
(sein Template-Modus zusätzlich `EDU_SHARING_URL`: die Konfigurationen und die
Kontext-Knoten liegen im Repositorium), `EDU_SHARING_TEXT_EXTRACTION_URL` für
den Extraktionsdienst, `METADATA_AGENT_URL` für den Metadata Agent. Ein
Übersprungen heißt dort „nicht konfiguriert“, nicht „nicht abgedeckt“.

## Veröffentlichen

So entsteht die nächste Version mit Release-Tag:

1. **Nummer festlegen.** Vor 1.0, also hebt eine brechende Änderung die
   Minor-Stelle. Was im Changelog als BREAKING steht, ist eine.
2. **`pyproject.toml`** — `version` setzen, und die `__version__`-Zeile in
   beiden REFERENCE-Fassungen mit. 0.1.0 hat das getan und die Liste hat es
   nicht gesagt; ein Test schlägt jetzt fehl, bis alle drei übereinstimmen.
   Dieselbe Nummer steht an drei weiteren Stellen, jede mit eigener Wache: die
   `@v…`-Installationsbefehle in beiden READMEs und die gestützte Zeile in
   `SECURITY.md` -- niemand soll dort lesen, die Fassung, zu deren Installation
   man ihn gerade aufgefordert hat, werde nicht gestützt.
3. **`uv lock`** — der Lock hält die eigene Version des Projekts fest und
   driftet sonst; `--locked` in der CI schlägt dann beim nächsten Push an,
   und genau dafür ist es da.
4. **`CHANGELOG.md`** — den Versionseintrag samt Link-Referenz vorbereiten;
   `[Unreleased]` bleibt für spätere Änderungen bestehen. Gibt es bereits einen
   vorgemerkten Eintrag, diesen aktualisieren und keinen zweiten anlegen.
   Release-Datum und Entfernung des Pending-Hinweises folgen erst nach den
   erfolgreichen Release-Prüfungen.
5. **Grün vor dem Tag.** `ruff check .`, `mypy`, `pytest -q`, und die
   Live-Suiten gegen die Staging — `-m live` und `-m write`. Eine
   Veröffentlichung ist der eine Moment, in dem die Live-Beweise nicht
   optional sind. Verweigert die Instanz einen davon, sagt es der
   Changelog-Eintrag: welche Beweise vorliegen, welche nicht und warum.
   `-m write` braucht seit dem 21.09.2026 eine Toolpermission, die diesem
   Konto fehlt — der Schritt war in seiner ersten Fassung also gar nicht
   erfüllbar, und ein Schritt, den niemand erfüllen kann, wird still
   übergangen statt festgehalten; hinterher ist dann nicht mehr zu erkennen,
   ob er es wurde.
6. **Committen, dann ein annotierter Tag** mit der Nummer aus Schritt 1:
   `git tag -a v<Nummer> -m "<Nummer>"`, danach `git push --follow-tags`. Das
   ausgeschriebene Beispiel, das hier stand, nannte 0.3.0 -- und nannte es vier
   Veröffentlichungen später immer noch.
7. **Auf grüne CI am Tag warten**, bevor irgendwo etwas angekündigt wird.

Eine Veröffentlichung auf PyPI gibt es noch nicht; installiert wird aus dem
Repositorium.

## Sicherheit

Einen Weg gefunden, wie diese Bibliothek Zugangsdaten preisgibt oder etwas
holt, das niemand verlangt hat? [`SECURITY.md`](SECURITY.md) sagt, wohin
damit — bitte erst einmal nicht öffentlich.

## Autor

**Jan Schachtschabel.** Entwickelt unter
[`janschachtschabel/edu-sharing-python-client`](https://github.com/janschachtschabel/edu-sharing-python-client), veröffentlicht hier
unter [`openeduhub/edu-sharing-python-client`](https://github.com/openeduhub/edu-sharing-python-client); beide tragen denselben
`main`, die älteren Tags liegen im Entwicklungsrepositorium. Installiert wird
von hier, gemeldet wird hier — Issues ebenso wie die nichtöffentlichen
Hinweise aus [`SECURITY.md`](SECURITY.md).

## Lizenz

Apache-2.0
