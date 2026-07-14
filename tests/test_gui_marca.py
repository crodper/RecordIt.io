"""Glifo de marca (burbuja + barras) dibujado con Pillow para el lockup.

Se dibuja desde la geometría de brand/icon.svg (no se rasteriza el SVG), así
que basta comprobar que produce una imagen RGBA no vacía a la altura pedida.
"""
import gui.app as app


def test_glifo_marca_altura_y_modo():
    g = app._glifo_marca(34)
    assert g.mode == "RGBA"
    assert g.height == 34
    assert g.width > 0
    # No es transparente del todo: hay glifo pintado.
    assert g.getbbox() is not None


def test_glifo_marca_escala_con_la_altura():
    chico, grande = app._glifo_marca(20), app._glifo_marca(80)
    assert grande.height == 80 and chico.height == 20
    # Conserva la proporción (ancho/alto) al escalar.
    assert abs(chico.width / chico.height - grande.width / grande.height) < 0.05
