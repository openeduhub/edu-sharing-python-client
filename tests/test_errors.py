"""Fehler-Mapping.

Die Erwartungen stammen aus Messungen gegen edu-sharing 11.0 (Staging,
27.08.2026), nicht aus der Implementierung. Jeder Testfall nennt die Messung,
die ihn begruendet.
"""

import pytest

from edusharing.errors import (
    AuthenticationError,
    ConflictError,
    EduSharingError,
    NotFoundError,
    PermissionDeniedError,
    ServerError,
    ValidationError,
    at_least,
    error_from_response,
    redirect_error,
)

URL = "https://repo.example.test/edu-sharing/rest/node/v1/nodes/-home-/x/metadata"


def _body(error_class: str, message: str) -> str:
    """Die Antwortform von edu-sharing: error / message / stacktrace."""
    import json

    return json.dumps({
        "error": error_class,
        "message": message,
        "stacktrace": "\njava.lang.Exception: ...\n\tat org.edu_sharing.Intern(Foo.java:1)\n",
    })


# --- Status-Mapping -------------------------------------------------------

def test_401_ohne_body_ist_authentifizierungsfehler():
    """Gemessen: falsche Zugangsdaten -> 401 mit LEEREM Body (kein JSON).

    Der Parser darf daran nicht scheitern.
    """
    exc = error_from_response(401, URL, "")
    assert isinstance(exc, AuthenticationError)


def test_404_ist_nicht_gefunden():
    """Gemessen: unbekannte Node-ID -> 404 DAOMissingException."""
    exc = error_from_response(
        404, URL, _body("org.edu_sharing.restservices.DAOMissingException",
                        "InvalidNodeRefException: Node does not exist"))
    assert isinstance(exc, NotFoundError)


def test_403_ist_rechteproblem():
    """Gemessen: comments lesen ohne Comment-Permission -> 403 DAOSecurityException."""
    exc = error_from_response(
        403, URL, _body("org.edu_sharing.restservices.DAOSecurityException",
                        "InsufficientPermissionException: No permission"))
    assert isinstance(exc, PermissionDeniedError)


def test_400_ist_validierungsfehler():
    """Gemessen: unbekanntes Kriterium in ngsearch -> 400 DAOValidationException."""
    exc = error_from_response(
        400, URL, _body("org.edu_sharing.restservices.DAOValidationException",
                        "Could not find parameter virtual:parent_recursive"))
    assert isinstance(exc, ValidationError)


def test_409_ist_konflikt():
    """Aus der Praxis: addReference auf eine bereits vorhandene Referenz."""
    exc = error_from_response(
        409, URL, _body("org.edu_sharing.restservices.DAODuplicateNodeNameException",
                        "DuplicateChildNodeNameException"))
    assert isinstance(exc, ConflictError)


def test_echter_500_bleibt_serverfehler():
    exc = error_from_response(
        500, URL, _body("java.lang.NullPointerException", "Cannot invoke NodeRef.getId()"))
    assert isinstance(exc, ServerError)
    assert not isinstance(exc, AuthenticationError)


# --- Der Kernfall: fehlende Auth kommt als 500 ----------------------------

def test_500_not_allowed_for_guest_ist_authentifizierungsfehler():
    """Gemessen: GET /iam/v1/people/-home-/-me-/preferences ohne Auth
    antwortet mit **HTTP 500**, nicht 401:

        {"error": "java.lang.Exception", "message": "Not allowed for guest user"}

    Wer nur den Status liest, meldet einen Serverfehler und empfiehlt einen
    Wiederholungsversuch -- dabei fehlt schlicht die Anmeldung. Ein Retry
    darauf ist zwecklos und belastet das Repositorium.
    """
    exc = error_from_response(
        500, URL, _body("java.lang.Exception", "Not allowed for guest user"))
    assert isinstance(exc, AuthenticationError)


def test_500_node_does_not_exist_ist_ein_verstecktes_404():
    """Gemessen am 28.08.2026: /usage/v1/usages/node/{id}/collections antwortet
    fuer einen Knoten, den es nicht gibt, mit **500** -- waehrend der
    Knotenendpunkt fuer dieselbe ID ordentlich 404 sagt.

    Der Unterschied ist teuer: als Serverfehler wiederholt der Transport die
    Anfrage dreimal, und der Aufrufer, der NotFoundError abfaengt, sieht sie
    nicht. Der Suchindex haelt auf Staging Knoten, die es nicht mehr gibt --
    gemessen 4 von 25 -- also ist das kein Randfall."""
    fehler = error_from_response(
        500, URL, _body("org.edu_sharing.restservices.DAOException",
                        "org.edu_sharing.service.usage.UsageException: Node does "
                        "not exist: workspace://SpacesStore/1f71f84a"))
    assert isinstance(fehler, NotFoundError)


def test_ein_500_mit_anderem_daoexception_bleibt_serverfehler():
    """Die Gegenprobe: nicht jede DAOException ist ein fehlender Knoten."""
    fehler = error_from_response(
        500, URL, _body("org.edu_sharing.restservices.DAOException",
                        "java.lang.UnsupportedOperationException: Can not find "
                        "Quatschrecht"))
    assert isinstance(fehler, ServerError)


def test_500_access_is_denied_ist_ein_rechteproblem():
    """Gemessen am 28.08.2026: /node/v1/nodes/-home-/{id}/parents antwortet fuer
    fremdes Material mit **500 AccessDeniedException**, waehrend derselbe
    Endpunkt am eigenen Knoten ordentlich 403 sagt.

    Dieselbe teure Verwechslung wie beim Gastzugang: als Serverfehler wiederholt
    der Transport die Anfrage dreimal, obwohl sie nie gelingen kann."""
    fehler = error_from_response(
        500, URL, _body("org.alfresco.repo.security.permissions.AccessDeniedException",
                        "Access is denied."))
    assert isinstance(fehler, PermissionDeniedError)


def test_500_not_an_admin_ist_rechteproblem():
    """Gemessen (Skill wlo-edu-sharing-api): /rating/v1/ratings/.../history
    antwortet 500 NotAnAdminException. Auch das ist kein Serverfehler."""
    exc = error_from_response(
        500, URL, _body("org.edu_sharing.restservices.NotAnAdminException", "not an admin"))
    assert isinstance(exc, PermissionDeniedError)


# --- Was die Fehlermeldung zeigen darf ------------------------------------

def test_meldung_enthaelt_keinen_stacktrace():
    """edu-sharing liefert den vollen Java-Stacktrace mit internen Pfaden mit.
    Der gehoert nicht in die Meldung, die eine Anwendung anzeigt."""
    exc = error_from_response(
        404, URL, _body("org.edu_sharing.restservices.DAOMissingException", "Node does not exist"))
    text = str(exc)
    assert "org.edu_sharing.Intern" not in text
    assert "\tat " not in text


def test_meldung_nennt_status_und_ursache():
    exc = error_from_response(
        404, URL, _body("org.edu_sharing.restservices.DAOMissingException", "Node does not exist"))
    text = str(exc)
    assert "404" in text
    assert "Node does not exist" in text
    # Der Java-Klassenname ist die praezisere Kategorie -- er gehoert in die Meldung.
    assert "DAOMissingException" in text


def test_stacktrace_bleibt_zum_debuggen_erreichbar():
    exc = error_from_response(
        404, URL, _body("org.edu_sharing.restservices.DAOMissingException", "Node does not exist"))
    assert exc.stacktrace is not None
    assert "org.edu_sharing.Intern" in exc.stacktrace


def test_nicht_json_body_stuerzt_nicht_ab():
    """Manche Fehler kommen als HTML (Reverse-Proxy) oder leer zurueck."""
    exc = error_from_response(502, URL, "<html><body>error code: 522</body></html>")
    assert isinstance(exc, ServerError)
    assert exc.error_class is None


@pytest.mark.parametrize("status", [400, 404, 500, 502])
@pytest.mark.parametrize("feld", [{"code": 502, "message": "Bad gateway"}, True, 42, ["x"]])
def test_ein_fehlerfeld_ohne_text_stuerzt_nicht_ab(status, feld):
    """Audit COR-23-1 (23.09.2026): ``error`` wurde als Java-Klassenname
    genommen, was immer es war. Ein Gateway, eine WAF oder ein Anmelde-Proxy
    vor dem Repositorium antwortet gern mit ``{"error": {...}}`` -- die
    b-api-Seite kennt diese Form seit dem 11.09.2026, diese nicht. Gemessen:
    ``AttributeError`` statt eines Fehlers dieser Bibliothek."""
    import json

    exc = error_from_response(status, URL, json.dumps(
        {"error": feld, "message": "abgelehnt", "stacktrace": {"kein": "text"}}))
    assert isinstance(exc, EduSharingError)
    assert exc.status == status
    assert exc.error_class is None
    assert exc.stacktrace is None
    assert "abgelehnt" in str(exc)


def test_attribute_sind_gesetzt():
    exc = error_from_response(
        400, URL, _body("org.edu_sharing.restservices.DAOValidationException", "kaputt"))
    assert exc.status == 400
    assert exc.url == URL
    assert exc.error_class == "org.edu_sharing.restservices.DAOValidationException"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 500, 502])
def test_alles_erbt_von_edusharingerror(status):
    """Ein Aufrufer kann pauschal EduSharingError fangen."""
    assert isinstance(error_from_response(status, URL, ""), EduSharingError)


def test_verborgene_details_werden_benannt():
    """Gemessen am 28.08.2026 gegen die Produktivinstanz redaktion.openeduhub.net.

    Sie setzt ``security.logging.displayLevel`` so, dass Fehlermeldungen nicht
    ausgeliefert werden::

        {"error": "java.lang.Exception",
         "message": "Details hidden: You can configure the output via
                     security.logging.displayLevel"}

    Damit greifen zwei der drei 5xx-Heuristiken nicht mehr: _GUEST_HINT und
    _MISSING_HINT lesen den Meldungstext, und der ist weg. Gemessen kostet das
    an derselben Adresse **4 Anfragen statt 1**, weil der Transport den
    ServerError dreimal wiederholt -- genau der Schaden, den die
    Gast-Erkennung verhindern soll.

    Einordnen laesst sich das nicht: was der Server verschweigt, kann die
    Bibliothek nicht erraten. Sagen laesst es sich aber -- sonst raetselt ein
    Entwickler, warum dieselbe Bibliothek gegen zwei Instanzen verschiedene
    Fehlertypen liefert.
    """
    exc = error_from_response(
        500, URL, _body("java.lang.Exception",
                        "Details hidden: You can configure the output via "
                        "security.logging.displayLevel"))
    text = str(exc)
    assert "security.logging.displayLevel" in text
    assert "could not tell" in text, (
        f"die Meldung sagt nicht, dass die Einordnung darunter leidet: {text}")


def test_sichtbare_details_bekommen_keinen_zusatz():
    """Der Hinweis darf nur erscheinen, wo er zutrifft."""
    exc = error_from_response(
        500, URL, _body("java.lang.Exception", "Something genuinely broke"))
    assert "could not tell" not in str(exc)


# --- Umleitungen -----------------------------------------------------------
#
# Eine ``Location`` ist Fremdtext: sie kommt vom Server, landet in ``str(exc)``,
# in den Logs und ueber ``as_result`` im Modellkontext. Eine vorsignierte
# Adresse traegt ihre Vollmacht in der Abfrage (``X-Amz-Signature=...``), ein
# Anmelde-Bounce sein Ticket -- beides einmal ausgesprochen ist beides
# weitergegeben. Das *Ziel* ist die Diagnose, der Rest ist es nicht (Audit
# SEC-6).

def _umleitung(location):
    return redirect_error(302, location, "https://repo.test/rest/_about",
                          service="the repository", env_var="EDU_SHARING_URL")


def test_eine_umleitung_nennt_den_host():
    """Ohne das Ziel ist die Meldung nutzlos -- es ist die eine Angabe, mit der
    jemand entscheidet, ob sein Proxy oder ein Fremder umgelenkt hat."""
    assert "cdn.test" in str(_umleitung("https://cdn.test/datei.pdf"))


def test_eine_vorsignierte_adresse_wird_nicht_ausgesprochen():
    fehler = _umleitung(
        "https://cdn.test/d.pdf?X-Amz-Signature=GEHEIM&X-Amz-Expires=900")
    assert "cdn.test" in str(fehler)
    assert "GEHEIM" not in str(fehler)
    assert "X-Amz-Signature" not in str(fehler)


def test_anmeldedaten_im_ziel_werden_nicht_ausgesprochen():
    """``netloc`` traegt die Anmeldedaten mit; der Hostname nicht."""
    fehler = _umleitung("https://nutzer:GEHEIM@cdn.test/datei.pdf")
    assert "cdn.test" in str(fehler)
    assert "GEHEIM" not in str(fehler)


def test_eine_relative_umleitung_spricht_gar_nichts_aus():
    """``/login?ticket=...`` hat keinen Host, aber ein Geheimnis im Pfad."""
    fehler = _umleitung("/login?ticket=GEHEIM")
    assert "GEHEIM" not in str(fehler)


def test_eine_kaputte_adresse_verdeckt_nicht_den_eigentlichen_fehler():
    """Den Header bestimmt die Gegenseite. Ein ``ValueError`` beim Bauen der
    Meldung wuerde die Umleitung durch einen Programmfehler ersetzen."""
    fehler = _umleitung("https://[::1/datei")
    assert fehler.status == 302
    assert "GEHEIM" not in str(fehler)


def test_ein_ipv6_ziel_bleibt_lesbar():
    """``hostname`` nimmt die Klammern weg, und ``::1:8080`` liest sich als
    weder Adresse noch Port (Pruefung 08.09.2026)."""
    assert "'[::1]:8080'" in str(_umleitung("https://[::1]:8080/x"))
    # Ohne Port ist nichts mehrdeutig, also auch nichts einzuklammern.
    assert "'fe80::1'" in str(_umleitung("https://[fe80::1]/y"))


def test_der_volle_wert_bleibt_zum_debuggen_erreichbar():
    """Verdeckt ist die *Meldung*, nicht die Angabe: wer die Umleitung
    nachvollziehen will, kommt an sie heran, ohne sie weiterzureichen."""
    voll = "https://cdn.test/d.pdf?X-Amz-Signature=GEHEIM"
    assert _umleitung(voll).location == voll


def test_ohne_location_bleibt_es_bei_none():
    fehler = _umleitung(None)
    assert fehler.location is None
    assert "without a Location header" in str(fehler)
    assert "`.location`" not in str(fehler), "es gibt nichts nachzulesen"


# --- at_least: die Endlichkeit (Audit API-23-3) -----------------------------

def test_at_least_lehnt_unendlich_ab():
    """Der Docstring sagte "Typ und Endlichkeit werden geprueft" -- geprueft
    wurde nan. ``Transport(url, timeout=inf)`` gab ``Timeout(timeout=inf)``,
    einen Aufruf, der nie aufgibt."""
    with pytest.raises(EduSharingError, match="timeout"):
        at_least("timeout", float("inf"), 0.001)


def test_at_least_erlaubt_unendlich_nur_wo_es_gesagt_wird():
    """``CACHE_FOREVER`` ist ``float("inf")`` -- dort ist Unendlich die
    Aussage, und der Aufrufer sagt es. Minus unendlich bleibt unter jeder
    Grenze."""
    at_least("cache_seconds", float("inf"), 0, infinite=True)
    with pytest.raises(EduSharingError):
        at_least("cache_seconds", float("-inf"), 0, infinite=True)
