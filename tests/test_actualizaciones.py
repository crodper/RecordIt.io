import json
import urllib.error

from recordit import actualizaciones


def _resp(payload):
    class _R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _R()


def test_es_mas_nueva():
    assert actualizaciones._es_mas_nueva("v0.6.0", "0.5.0") is True
    assert actualizaciones._es_mas_nueva("0.6.0", "0.6.0") is False
    assert actualizaciones._es_mas_nueva("v0.4.0", "0.5.0") is False
    assert actualizaciones._es_mas_nueva("no-version", "0.5.0") is False


def test_github_detecta_mas_nueva(monkeypatch):
    cap = {}

    def _urlopen(req, *a, **k):
        cap["url"] = req.full_url
        cap["ua"] = req.headers.get("User-agent")
        return _resp({
            "tag_name": "v0.6.0",
            "html_url": "https://github.com/crodper/RecordIt.io/releases/tag/v0.6.0",
            "body": "notas nuevas"})

    monkeypatch.setattr(actualizaciones.urllib.request, "urlopen", _urlopen)
    info = actualizaciones.comprobar_actualizacion("0.5.0")
    assert info == {
        "version": "0.6.0",
        "url": "https://github.com/crodper/RecordIt.io/releases/tag/v0.6.0",
        "notas": "notas nuevas"}
    assert cap["url"] == actualizaciones.GITHUB_API
    assert cap["ua"]  # GitHub exige User-Agent


def test_github_sin_novedad(monkeypatch):
    monkeypatch.setattr(
        actualizaciones.urllib.request, "urlopen",
        lambda req, *a, **k: _resp({"tag_name": "v0.5.0", "html_url": "x", "body": ""}))
    assert actualizaciones.comprobar_actualizacion("0.5.0") is None


def test_error_de_red_da_none(monkeypatch):
    def _urlopen(req, *a, **k):
        raise urllib.error.URLError("sin red")

    monkeypatch.setattr(actualizaciones.urllib.request, "urlopen", _urlopen)
    assert actualizaciones.comprobar_actualizacion("0.5.0") is None


def test_json_no_dict_da_none(monkeypatch):
    monkeypatch.setattr(actualizaciones.urllib.request, "urlopen",
                        lambda req, *a, **k: _resp(["algo", "raro"]))
    assert actualizaciones.comprobar_actualizacion("0.5.0") is None
