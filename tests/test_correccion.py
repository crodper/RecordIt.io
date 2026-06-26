from recordit import correccion


def test_normaliza_capitalizacion_desde_glosario():
    # 'modbus'/'zigbee' están en el glosario del repo -> forma canónica
    assert correccion.corregir("el modbus usa zigbee") == "el Modbus usa Zigbee"


def test_aplica_correccion_explicita_del_repo():
    # 'zig bee => Zigbee' está en correcciones.txt del repo
    assert correccion.corregir("pon el zig bee") == "pon el Zigbee"


def test_no_toca_texto_normal():
    assert correccion.corregir("hola qué tal la reunión") == "hola qué tal la reunión"


def test_respeta_limites_de_palabra():
    # 'OTA' del glosario no debe colarse dentro de otra palabra ('nota')
    assert correccion.corregir("toma nota de la reunión") == "toma nota de la reunión"


def test_expresion_larga_gana_a_la_corta(monkeypatch, tmp_path):
    # con 'BACnet' y 'BACnet IP' en glosario, "bacnet ip" -> "BACnet IP" (no "BACnet ip")
    g = tmp_path / "glosario.txt"
    g.write_text("BACnet IP\n", encoding="utf-8")
    monkeypatch.setattr(
        correccion.glosario.config, "ruta_glosario_usuario", lambda: g)
    assert correccion.corregir("usa bacnet ip hoy") == "usa BACnet IP hoy"


def test_correccion_luego_normaliza_capitalizacion():
    # 'zig bee => Zigbee' (explícita) y 'modbus' del glosario -> 'Modbus', en una pasada
    assert correccion.corregir("el zig bee con modbus") == "el Zigbee con Modbus"


def test_correccion_usuario_se_aplica(monkeypatch, tmp_path):
    usuario = tmp_path / "correcciones.txt"
    usuario.write_text("# comentario\nrest api => REST API\n", encoding="utf-8")
    monkeypatch.setattr(
        correccion.config, "ruta_correcciones_usuario", lambda: usuario)
    assert correccion.corregir("usa el rest api") == "usa el REST API"
