import sys

import grabar_reunion
from recordit import audio, rutas, transcripcion_vivo


class _VivoFake:
    def __init__(self):
        self.finalizado = False

    def alimentar(self, b):
        pass

    def finalizar(self):
        self.finalizado = True
        return True


def test_transcribir_crea_el_vivo_y_lo_finaliza(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    vivo = _VivoFake()
    capturado = {}

    def grabar_fake(salida, **kwargs):
        capturado.update(kwargs)
        return 1.0

    monkeypatch.setattr(audio, "grabar", grabar_fake)
    monkeypatch.setattr(audio, "frecuencia_soportada", lambda d, f, c: f)
    monkeypatch.setattr(transcripcion_vivo, "crear", lambda base, f: vivo)
    monkeypatch.setattr(sys, "argv", ["grabar_reunion.py", "--transcribir",
                                      "-o", str(tmp_path / "reunion_t.wav")])
    grabar_reunion.main()
    assert capturado["muestras_callback"] == vivo.alimentar
    assert vivo.finalizado is True
    assert "Transcripción lista" in capsys.readouterr().out


def test_sin_flag_no_hay_transcripcion_en_vivo(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDIT_DATA_DIR", str(tmp_path))
    capturado = {}
    monkeypatch.setattr(audio, "grabar",
                        lambda salida, **kwargs: capturado.update(kwargs) or 1.0)
    monkeypatch.setattr(sys, "argv", ["grabar_reunion.py",
                                      "-o", str(tmp_path / "reunion_t.wav")])
    grabar_reunion.main()
    assert capturado["muestras_callback"] is None
