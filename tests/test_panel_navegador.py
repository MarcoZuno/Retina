"""El panel de verdad, en un navegador sin ventana: lo que ve un juez en inglés y lo que ve quien edita en español.

Necesita Playwright con Chromium (pip install playwright, playwright install chromium). Sin él, estas pruebas se saltan;
la lista de frases prohibidas de abajo corre siempre. Ningún caso real: se parte del ejemplo inventado y se cambia lo
que cada prueba necesita. Nada de esto llama a una API.
"""
from __future__ import annotations

import functools
import json
import re
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from retina.demo import ServidorExclusivo, SoloElPanel
from retina.esquemas import RAIZ

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

PANEL = RAIZ / "panel" / "index.html"
ID = "aaaaaaaaaaaa"  # un caso subido: doce letras hexadecimales
CASO = f"/casos/{ID}/resultado.json"
ES = re.compile(r"\b(tu|tus|qué|cómo|personas|revisión|inicio|normas|según|también|cuadros|fondo|detalles)\b", re.I)
EN = re.compile(r"\b(your|the|opening|people|review|what|how|rules|frames|background|details)\b", re.I)
VISTOS = """() => {  // lo que se lee: texto visible y lo que oye quien usa lector de pantalla
  const textos = [document.body.innerText];
  for (const n of document.querySelectorAll("[aria-label], [title], [alt]"))
    if (n.checkVisibility()) textos.push(n.getAttribute("aria-label") || "", n.getAttribute("title") || "", n.getAttribute("alt") || "");
  return textos.join("\\n");
}"""


def demo(carpeta: str = "demo-en") -> dict:
    return json.loads((RAIZ / "casos" / carpeta / "resultado.json").read_text(encoding="utf-8"))


class Frases(unittest.TestCase):
    """Lo que la auditoría pidió quitar no vuelve, aunque no haya navegador."""

    def setUp(self):
        self.panel = PANEL.read_text(encoding="utf-8")

    def test_no_vuelven_las_frases_retiradas(self):
        for frase in ("1.5 veces", "1.5 times", "3.5 veces", "3.5 times", "por_que_importa", "puede fallar", "can be off", "give or take",
                      "como el tuyo", "like yours", "Es parecido", "similar to videos", "9 de 10", "9 in 10", "Tres cuadros listos",
                      "Three frames ready", "vacio_p2", "Failed to fetch", "Esto es lo que vimos"):
            self.assertNotIn(frase, self.panel, frase)

    def test_las_frases_pedidas_estan_tal_cual(self):
        for frase in ("Suele fallar por unas ${m} personas de cada 100; 4 de cada 10 veces, por más.",
                      "Usually off by about ${m} of every 100 people; 4 in 10 times, by more.",
                      "No vemos diferencia con la curva de su duración", "We see no difference from the curve for its length",
                      "Tu video actual", "Your current video", "No pudimos comprobarlo en este idioma", "Da una sola prueba, no toda la lista",
                      "Gives one proof, not the whole list", "USD 0.05 a 0.25", "USD 0.05 to 0.25"):
            self.assertIn(frase, self.panel, frase)


@unittest.skipIf(sync_playwright is None, "sin Playwright")
class Navegador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manejador = functools.partial(type("Silencioso", (SoloElPanel,), {"log_message": lambda *a: None}), directory=str(RAIZ))
        cls.servidor = ServidorExclusivo(("127.0.0.1", 0), manejador)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}/panel/"
        cls.pw = sync_playwright().start()
        cls.navegador = cls.pw.chromium.launch(args=["--disable-webgl", "--disable-webgl2"])  # el vidrio no se prueba aquí y por software tarda

    @classmethod
    def tearDownClass(cls):
        cls.navegador.close()
        cls.pw.stop()
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def test_la_direccion_sin_panel_lleva_al_panel(self):
        import urllib.request
        with urllib.request.urlopen(self.url.removesuffix("panel/")) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(r.geturl().endswith("/panel/"))

    def setUp(self):
        self.contextos = []

    def tearDown(self):
        for c in self.contextos:
            c.close()

    def pagina(self, locale="en-US", ancho=1280):
        c = self.navegador.new_context(locale=locale, viewport={"width": ancho, "height": 900})
        self.contextos.append(c)
        p = c.new_page()
        p.errores = []
        p.on("pageerror", lambda e: p.errores.append(str(e)))
        p.add_init_script("""window.__estados = [];
          new MutationObserver(() => { const e = document.body && document.body.dataset.estado; if (e && window.__estados.at(-1) !== e) window.__estados.push(e); })
            .observe(document, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-estado"] });""")
        return p

    def con_caso(self, p, r: dict, subida: bool = False):
        """Sirve `r` como un caso subido, con los dibujos del ejemplo. Con `subida`, la página cree estar en la app."""
        cuerpo = json.dumps(r, ensure_ascii=False)
        p.route(lambda u: urlsplit(u).path == CASO,  # por ruta exacta: la dirección de la página también lleva el caso, en ?caso=
                lambda ruta: ruta.fulfill(status=200, content_type="application/json", body=cuerpo))
        p.route(f"**/casos/{ID}/*.webp", lambda ruta: ruta.fulfill(path=str(RAIZ / "casos" / "demo-en" / ruta.request.url.rsplit("/", 1)[1])))
        if subida:
            p.route("**/api/salud", lambda ruta: ruta.fulfill(status=200, content_type="application/json",
                                                              body='{"subir": true, "ffmpeg": true, "llave": true, "acceso": false}'))
            p.route("**/api/talentos", lambda ruta: ruta.fulfill(status=200, content_type="application/json", body='{"talentos": []}'))
        p.goto(f"{self.url}?caso={CASO}")
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        return p

    def abre(self, r: dict, locale="en-US", subida=False):
        return self.con_caso(self.pagina(locale), r, subida)

    def espera(self, p, condicion: str, tope_s: float = 15) -> None:
        """Con evaluate y no con wait_for_function: la CSP del panel prohíbe el eval que esa función necesita, y se queda puesta."""
        fin = time.monotonic() + tope_s
        while time.monotonic() < fin:
            try:
                if p.evaluate(condicion):
                    return
            except Exception:  # noqa: BLE001 - la página está navegando
                pass
            p.wait_for_timeout(40)
        self.fail(f"no se cumplió: {condicion}")

    def texto(self, p, selector: str) -> str:
        return p.locator(selector).inner_text()

    def visible(self, p, selector: str) -> bool:
        return p.locator(selector).is_visible()

    # ---- X1: el idioma y su caso ----
    def test_el_juez_en_ingles_ve_todo_en_ingles_sin_tocar_nada(self):
        p = self.pagina("en-US")
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertEqual(p.evaluate("document.documentElement.lang"), "en")
        self.assertIn("Made-up example", self.texto(p, "#titulo-video"))
        self.assertEqual(ES.findall(p.evaluate(VISTOS)), [])
        self.assertEqual(p.errores, [])

    def test_en_espanol_todo_en_espanol_sin_tocar_nada(self):
        p = self.pagina("es-MX")
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertEqual(p.evaluate("document.documentElement.lang"), "es")
        self.assertIn("Ejemplo inventado", self.texto(p, "#titulo-video"))
        self.assertEqual([x for x in EN.findall(p.evaluate(VISTOS)) if x != "English"], [])

    def test_el_boton_cambia_de_ejemplo_y_recorre_todo_sin_mezclar(self):
        p = self.pagina("en-US")
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        p.locator("#idioma").click()
        self.espera(p, "document.getElementById('titulo-video').textContent.startsWith('Ejemplo')")
        p.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = true; })")
        self.assertEqual(EN.findall(p.evaluate(VISTOS)), [])
        p.locator("#idioma").click()
        self.espera(p, "document.getElementById('titulo-video').textContent.startsWith('Made-up')")
        p.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = true; })")
        self.assertEqual(ES.findall(p.evaluate(VISTOS)), [])

    def test_lo_que_elige_la_persona_gana_al_navegador(self):
        p = self.pagina("en-US")
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        p.locator("#idioma").click()
        self.espera(p, "document.documentElement.lang === 'es'")
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertIn("Ejemplo inventado", self.texto(p, "#titulo-video"))

    def test_un_caso_explicito_se_respeta(self):
        p = self.pagina("en-US")
        p.goto(f"{self.url}?caso=/casos/demo/resultado.json")
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertIn("Ejemplo inventado", self.texto(p, "#titulo-video"))
        p.locator("#idioma").click()  # y el botón lleva al otro ejemplo, no deja el caso a medias
        self.espera(p, "document.getElementById('titulo-video').textContent.startsWith('Ejemplo') && document.documentElement.lang === 'es'")

    # ---- X2: una falla pasajera no se nota y la pantalla de JSON no aparece donde se puede subir ----
    def test_una_falla_pasajera_de_salud_no_se_nota(self):
        p = self.pagina()
        veces = []

        def salud(ruta):
            veces.append(1)
            ruta.abort() if len(veces) < 3 else ruta.fulfill(status=200, content_type="application/json", body='{"subir": false}')

        p.route("**/api/salud", salud)
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertEqual(len(veces), 3)
        self.assertFalse(self.visible(p, "#error"))
        self.assertNotIn("vacio", p.evaluate("window.__estados"))

    def test_con_la_app_nunca_sale_la_pantalla_de_json_aunque_salud_tarde_en_contestar(self):
        p = self.pagina()
        veces = []

        def salud(ruta):
            veces.append(1)
            if len(veces) < 3:
                return ruta.fulfill(status=503, body="")
            ruta.fulfill(status=200, content_type="application/json", body='{"subir": true, "ffmpeg": true, "llave": true}')

        p.route("**/api/salud", salud)
        p.route("**/api/talentos", lambda r: r.abort())
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'subir'")
        self.assertNotIn("vacio", p.evaluate("window.__estados"))
        self.assertFalse(self.visible(p, "#error"))

    def test_si_retina_no_contesta_se_ofrece_reintentar_sin_rojo(self):
        p = self.pagina()
        cerrado = {"si": True}

        def salud(ruta):
            ruta.abort() if cerrado["si"] else ruta.fulfill(status=200, content_type="application/json", body='{"subir": false}')

        p.route("**/api/salud", salud)
        p.goto(self.url)
        p.locator("#reintentar").wait_for(state="visible")
        self.assertFalse(self.visible(p, "#error"))
        self.assertNotIn("vacio", p.evaluate("window.__estados"))
        cerrado["si"] = False
        p.locator("#reintentar").click()
        self.espera(p, "document.body.dataset.estado === 'resultado'")

    # ---- X4, X5, X6: de qué es el número y cómo se dice ----
    def test_el_numero_es_del_video_actual(self):
        p = self.abre(demo())
        self.assertEqual(self.texto(p, ".etiqueta-actual"), "Your video as it is today, before any change")
        principal = p.locator(".cifra.personas")
        self.assertIn("Usually off by about 11 of every 100 people; 4 in 10 times, by more.", principal.inner_text())
        p.locator(".de-donde summary").click()
        self.assertIn("It doesn't measure the new opening", principal.inner_text())

    def test_sin_diferencia_lo_dice_con_la_frase_nueva(self):
        r = demo()
        r["prediccion"]["curva_parecidos"] = list(r["prediccion"]["curva_predicha"])
        p = self.abre(r)
        self.assertIn("We see no difference from the curve for its length.", self.texto(p, ".texto-gente"))

    # ---- P4, P7: el lazo ----
    def test_el_lazo_cuenta_que_fallo_en_cada_vuelta(self):
        r = demo()
        r["apertura"].update(vueltas=2, intentos=[
            {"vuelta": 0, "problemas": [{"id": "cifras", "detalle": "cifras que no vienen en los datos del video: 35"}]},
            {"vuelta": 1, "problemas": [{"id": "largo", "detalle": "la voz mide 60 palabras y tiene que medir de 18 a 45"}]},
            {"vuelta": 2, "problemas": []}])
        p = self.abre(r)
        historia = self.texto(p, "#apertura-lazo")
        self.assertIn("Retina rejected it 2 times and fixed it", historia)
        self.assertIn("numbers your video doesn't say: 35", historia)
        self.assertIn("It was 60 words long and must be 18 to 45", historia)
        self.assertEqual(p.locator("#lazo-lista li").count(), 3)
        self.assertEqual(ES.findall(historia), [])

    def test_a_la_primera_se_dice_sin_inflarlo(self):
        r = demo()
        r["apertura"].update(vueltas=0, intentos=[{"vuelta": 0, "problemas": []}])
        p = self.abre(r)
        self.assertIn("Passed on the first try", self.texto(p, "#apertura-lazo"))
        self.assertEqual(p.locator("#lazo-lista li").count(), 1)

    def test_la_falla_ensena_su_motivo_real(self):
        r = demo()
        r["apertura"].update(aprobada=False, despues=None, vueltas=2, comprobaciones=[{"id": "intocables", "paso": False}, {"id": "tema", "paso": True}],
                             intentos=[{"vuelta": i, "problemas": [{"id": "intocables", "detalle": "toca algo intocable: postura"}]} for i in range(3)])
        p = self.abre(r)
        lista = self.texto(p, "#apertura-comprobada")
        self.assertIn("postura", lista)
        self.assertNotIn("Doesn't touch logos", lista)
        self.assertIn("so we're not showing you one", self.texto(p, "#apertura-lazo"))
        self.assertFalse(self.visible(p, "#antes-despues"))

    def test_un_motivo_desconocido_no_se_cuela_en_espanol_al_panel_en_ingles(self):
        r = demo()
        r["apertura"]["intentos"] = [{"vuelta": 0, "problemas": [{"id": "regla_nueva", "detalle": "algo en español"}]}, {"vuelta": 1, "problemas": []}]
        r["apertura"]["vueltas"] = 1
        self.assertNotIn("español", self.texto(self.abre(r), "#apertura-lazo"))

    # ---- P2: los cuadros ----
    def test_los_cuadros_sin_revisar_se_dicen(self):
        r = demo()
        r["apertura"]["despues"]["cuadros_revisados"] = [{"cuadro": 2, "coincide": True}, {"cuadro": 3, "coincide": None}]
        p = self.abre(r)
        lista = p.locator("#apertura-comprobada").inner_text()
        self.assertIn("frame 2 shows what it says", lista)
        self.assertIn("Frame 3 couldn't be checked", lista)
        self.assertNotIn("Three frames", lista)
        self.assertEqual(self.texto(p, ".miniaturas .sin-revisar"), "Not checked")

    def test_todos_revisados_y_ninguno_marcado(self):
        r = demo()
        r["apertura"]["despues"]["cuadros_revisados"] = [{"cuadro": 2, "coincide": True}, {"cuadro": 3, "coincide": True}]
        p = self.abre(r)
        self.assertIn("frames 2 and 3 show what they say", self.texto(p, "#apertura-comprobada"))
        self.assertEqual(p.locator(".sin-revisar").count(), 0)

    def test_sin_el_campo_no_se_finge_que_se_revisaron(self):
        r = demo()
        del r["apertura"]["despues"]["cuadros_revisados"]
        self.assertIn("Frames 2 and 3 weren't checked", self.texto(self.abre(r), "#apertura-comprobada"))

    # ---- lo que encontró la revisión con ojos de jurado ----
    def test_el_inicio_va_antes_que_el_numero(self):
        p = self.abre(demo())
        self.assertLess(p.locator("#bloque-apertura").bounding_box()["y"], p.locator("#cifras").bounding_box()["y"])

    def test_salud_y_fuera_no_se_reescriben(self):
        r = demo()
        r["apertura"].update(aprobada=False, despues=None, vueltas=0, intentos=[], comprobaciones=[], fuera_de_alcance="salud")
        p = self.abre(r)
        self.assertIn("doesn't rewrite health advice", self.texto(p, "#apertura-resumen"))
        self.assertFalse(self.visible(p, "#antes-despues"))

    def test_lo_que_no_se_comprobo_no_dice_que_paso_todo(self):
        r = demo()
        r["apertura"]["no_comprobe"] = ["fidelidad"]
        p = self.abre(r)
        self.assertIn("couldn't finish checking it", self.texto(p, "#sub"))
        self.assertIn("Not fully checked.", self.texto(p, "#apertura-lazo"))
        self.assertIn("couldn't read it against your video", p.locator("#apertura-comprobada").inner_text())

    def test_el_ejemplo_no_se_firma_como_de_un_modelo(self):
        self.assertNotIn("according to Muse Spark Open", self.abre(demo()).locator("body").inner_text())

    def test_el_credito_se_ve_arriba(self):
        self.assertTrue(self.visible(self.abre(demo()), ".hecho-arriba"))

    # ---- apertura.ya_funciona y modo sin voz ----
    def test_el_inicio_que_ya_funciona_es_un_logro(self):
        r = demo()
        r["apertura"].update(ya_funciona=True, motivo="It says the topic right away.", aprobada=True, despues=None, comprobaciones=[],
                             vueltas=0, intentos=[{"vuelta": 0, "problemas": []}])
        p = self.abre(r, subida=True)
        self.assertEqual(self.texto(p, "#titular"), "Your opening already works")
        self.assertIn("It says the topic right away.", self.texto(p, "#apertura-ya"))
        self.assertFalse(self.visible(p, "#arreglar"))
        self.assertFalse(self.visible(p, "#antes-despues"))
        self.assertFalse(self.visible(p, "#error"))

    def test_video_mudo_es_texto_en_pantalla_y_no_se_lee_en_voz_alta(self):
        r = demo()
        r["apertura"]["modo"] = "texto_en_pantalla"
        p = self.abre(r)
        self.assertEqual(self.texto(p, ".lado.nuevo .rotulo-voz"), "On-screen text")
        self.assertEqual(self.texto(p, "#reproducir"), "▶ Watch the new opening")
        p.evaluate("window.__dichas = 0; speechSynthesis.speak = () => { window.__dichas += 1; }; 0")
        p.locator("#reproducir").click()
        self.assertEqual(p.evaluate("window.__dichas"), 0)

    # ---- titulo_contra_video ----
    def test_el_aviso_del_titulo_solo_si_no_cumple(self):
        for cumple, se_ve in (("parcial", True), ("no", True), ("si", False), (None, False)):
            with self.subTest(cumple=cumple):
                r = demo()
                r["titulo_contra_video"] = {"cumple": cumple, "por_que": "It only covers one trick."}
                p = self.abre(r)
                self.assertEqual(self.visible(p, "#aviso-titulo"), se_ve)
                if se_ve:
                    self.assertIn("It only covers one trick.", self.texto(p, "#aviso-titulo"))

    # ---- P5: normas ----
    def test_con_anzuelo_nunca_dice_sin_riesgos(self):
        r = demo()
        r["explicacion"].update(anzuelo_detectado="pide_interaccion", anzuelo_frase="Share this", anzuelo_momento_s=4)
        p = self.abre(r)
        resumen = self.texto(p, "#normas-resumen")
        self.assertIn("We found 1 point", resumen)
        self.assertNotIn("no clear risks", resumen)
        self.assertIn("Share this", self.texto(p, "#normas-lista"))

    def test_el_anzuelo_que_ya_viene_en_normas_no_se_cuenta_dos_veces(self):
        r = demo()
        r["explicacion"].update(anzuelo_detectado="pide_interaccion", anzuelo_frase="Share this", anzuelo_momento_s=4)
        r["normas"]["hallazgos"] = [{"nombre": "Engagement bait", "por_que": "It asks.", "evidencia": "Share this", "segundo": 4}]
        self.assertIn("We found 1 point", self.texto(self.abre(r), "#normas-resumen"))

    def test_lo_no_verificado_nunca_dice_sin_riesgos(self):
        r = demo()
        r["normas"]["no_verificado"] = True
        resumen = self.texto(self.abre(r), "#normas-resumen")
        self.assertEqual(resumen, "We couldn't check this in this language.")

    # ---- P6, P8: antes de subir, y traducir solo si se pide ----
    def test_antes_de_subir_se_dice_a_donde_va_y_cuanto_cuesta(self):
        p = self.pagina()
        p.route("**/api/salud", lambda r: r.fulfill(status=200, content_type="application/json", body='{"subir": true, "ffmpeg": true, "llave": true}'))
        p.route("**/api/talentos", lambda r: r.fulfill(status=200, content_type="application/json", body='{"talentos": []}'))
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'subir'")
        aviso = self.texto(p, ".nota-envio")
        for parte in ("Meta", "Baseten", "USD 0.10", "USD 0.05 to 0.25"):
            self.assertIn(parte, aviso)

    def test_abrir_un_caso_nunca_traduce_y_el_boton_si(self):
        r = demo("demo")
        r["idioma"] = "es"
        p = self.pagina()
        pedidos = []

        def traducir(ruta):
            pedidos.append(ruta.request.method)
            ruta.fulfill(status=200, content_type="application/json", body=json.dumps({**r, "idioma": "en"}, ensure_ascii=False))

        p.route("**/api/traducir/**", traducir)
        self.con_caso(p, r, subida=True)
        self.assertEqual(pedidos, [])
        self.assertTrue(self.visible(p, "#traducir"))
        p.locator("#traducir").click()
        self.espera(p, "document.getElementById('aviso-idioma').classList.contains('oculto')")
        self.assertEqual(pedidos, ["POST"])

    def test_failed_to_fetch_nunca_se_ve(self):
        r = demo("demo")
        r["idioma"] = "es"
        p = self.pagina()
        p.route("**/api/traducir/**", lambda ruta: ruta.abort())
        self.con_caso(p, r, subida=True)
        p.locator("#traducir").click()
        self.espera(p, "!document.getElementById('traducir').classList.contains('oculto')")
        self.assertEqual(self.texto(p, "#aviso-idioma-texto"), "We couldn't translate the review: it stays in its original language.")

    def test_un_archivo_que_no_es_json_no_ensena_el_error_de_javascript(self):
        p = self.pagina()
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        p.locator("#archivo").set_input_files({"name": "x.json", "mimeType": "application/json", "buffer": b"esto no es json"})
        p.locator("#error").wait_for(state="visible")
        self.assertNotIn("Unexpected", self.texto(p, "#error"))

    # ---- P10, P11 ----
    def test_copiar_sigue_sin_cambio_sugerido(self):
        r = demo()
        r["explicacion"].update(que_cambiar="", pasos=[], mejoras_opcionales=[])
        p = self.abre(r)
        self.assertTrue(self.visible(p, "#copiar"))
        self.assertIn("Retina", p.evaluate("textoParaEditor()"))

    def test_los_tiempos_se_leen_bien(self):
        p = self.pagina()
        p.goto(self.url)
        self.espera(p, "document.body.dataset.estado === 'resultado'")
        self.assertEqual(p.evaluate("mmss(59.6)"), "1:00")
        self.assertEqual(p.evaluate("mmss(119.7)"), "2:00")
        self.assertEqual(p.evaluate("reloj('Del segundo 6 al 6 se pierde')"), "En el 0:06 se pierde")
        self.assertEqual(p.evaluate("reloj('corta del segundo 6.1 al 6.3')"), "corta en el 0:06")
        self.assertEqual(p.evaluate("reloj('From second 6 to 6')"), "At 0:06")
        self.assertEqual(p.evaluate("reloj('del segundo 4 al 11')"), "del 0:04 al 0:11")

    def test_la_voz_se_calla_al_salir(self):
        p = self.abre(demo())
        p.evaluate("window.__cancelada = 0; const c = speechSynthesis.cancel.bind(speechSynthesis); speechSynthesis.cancel = () => { window.__cancelada += 1; c(); }; 0")
        p.locator("#reproducir").click()
        antes = p.evaluate("window.__cancelada")
        p.locator("#otra").click()
        self.assertGreater(p.evaluate("window.__cancelada"), antes)
        self.assertEqual(p.evaluate("arranqueSonando"), None)

    def test_lo_que_no_se_pudo_verificar_se_muestra(self):
        r = demo()
        r["explicacion"]["no_pude_verificar"] = ["The background music."]
        p = self.abre(r)
        p.locator("#mas-detalles > summary").click()
        p.locator("#mas-detalles details summary").last.click()
        self.assertIn("We couldn't verify: The background music.", self.texto(p, "#detalle-lista"))

    def test_sin_cambio_lo_no_verificado_sale_a_la_vista(self):
        r = demo()
        r["arranque"]["nivel"] = "alto"
        r["explicacion"].update(que_cambiar="", pasos=[], no_pude_verificar=["The second half."])
        self.assertIn("The second half.", self.texto(self.abre(r), "#sin-verificar"))

    def test_otros_estados_del_titular(self):
        r = demo()
        self.assertEqual(self.texto(self.abre(r), "#titular"), "Here's a new opening for your video")
        del r["apertura"]
        self.assertEqual(self.texto(self.abre(r), "#titular"), "What you can change in your video's opening")

    # ---- comparar ----
    def test_comparar_en_ingles_usa_las_reglas_en_ingles(self):
        p = self.pagina()
        a, b = "a" * 12, "b" * 12
        es = demo("demo")
        p.route("**/casos/*/resultado.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(es, ensure_ascii=False)))
        p.route("**/casos/*/comparacion.json", lambda r: r.fulfill(status=404, body=""))
        p.goto(f"{self.url}?a={a}&b={b}")
        self.espera(p, "document.body.dataset.estado === 'comparacion'")
        self.assertIn("Something that stops people in the first 3 seconds", self.texto(p, "#c-tabla"))

    # ---- En todos los anchos ----
    def test_sin_scroll_horizontal(self):
        for ancho in (390, 768, 1440):
            for carpeta in ("demo", "demo-en"):
                with self.subTest(ancho=ancho, caso=carpeta):
                    p = self.pagina(ancho=ancho)
                    p.goto(f"{self.url}?caso=/casos/{carpeta}/resultado.json")
                    self.espera(p, "document.body.dataset.estado === 'resultado'")
                    self.assertLessEqual(p.evaluate("document.documentElement.scrollWidth"), ancho)


if __name__ == "__main__":
    unittest.main()
