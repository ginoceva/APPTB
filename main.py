import flet as ft
import sqlite3
import pandas as pd
import openpyxl
import os
import unicodedata
import webbrowser 
import urllib.parse
from datetime import datetime

# --- CONFIGURACIÓN DE RUTAS ---
# Detectamos si estamos en un entorno Android
IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_ROOT" in os.environ

if IS_ANDROID:
    # En Android Flet, base dir suele ser el root extraido
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Carpeta escribible segura (internal storage de la app)
    WRITE_DIR = os.path.expanduser("~")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    WRITE_DIR = BASE_DIR

# Archivos en assets (lectura)
DB_PATH = os.path.join(BASE_DIR, "assets", "datos_logistica.db")
USUARIOS_PATH = os.path.join(BASE_DIR, "assets", "Usuarios.xlsx")

# Archivo de salida (escritura)
REPORTE_PATH = os.path.join(WRITE_DIR, "Reporte_Escaneos.xlsx")

# --- VARIABLES VISUALES Y COLORES ---
COLOR_AZUL_CEVA = "#002060"
COLOR_ROJO_CEVA = "#C00000"
COLOR_VERDE_OK = "#28a745"
COLOR_NARANJA_WARN = "#FF8C00"
COLOR_FONDO = "#FFFFFF"

def main(page: ft.Page):
    # Configuración Inicial
    page.title = "CEVA Logistics Offline"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.window_width = 380
    page.window_height = 800
    page.bgcolor = COLOR_FONDO
    page.scroll = "adaptive"

    # --- ESTADO GLOBAL ---
    state = {
        "usuario": "",
        "modelo": "",
        "box_calculado": "",
        "semana_full": "",
        "piezas_teoricas": [], # list de tuplas (Box, Material, Medio)
        "piezas_escaneadas": [], # list de codigos
        "faltantes": [],
        "codigo_unico": "",
        "medio_esperado_actual": "",
        "ruta_foto_box": None,
        "ruta_foto_lista": None
    }

    # ==========================================
    # HERRAMIENTAS GLOBALES Y FUNCIONES AUX
    # ==========================================
    
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)
    
    def on_dialog_result(e: ft.FilePickerResultEvent):
        if e.files:
            path = e.files[0].path
            if page.data == "BOX":
                state["ruta_foto_box"] = path
                page.snack_bar = ft.SnackBar(ft.Text("Foto BOX cargada"), bgcolor=COLOR_VERDE_OK)
            elif page.data == "LISTA":
                state["ruta_foto_lista"] = path
                page.snack_bar = ft.SnackBar(ft.Text("Foto LISTA cargada"), bgcolor=COLOR_VERDE_OK)
            page.snack_bar.open = True
            if page.route == "/listado":
                mostrar_listado()
            else:
                page.update()

    file_picker.on_result = on_dialog_result
    page.data = "" 

    def normalizar_texto(texto):
        if not texto: return ""
        texto = str(texto).upper()
        texto = unicodedata.normalize('NFKD', texto)
        texto_sin_tildes = "".join([c for c in texto if not unicodedata.combining(c)])
        return texto_sin_tildes.replace(" ", "").strip()

    def guardar_registro_excel(datos):
        try:
            df_nuevo = pd.DataFrame([datos])
            if os.path.exists(REPORTE_PATH):
                df_existente = pd.read_excel(REPORTE_PATH)
                df_final = pd.concat([df_existente, df_nuevo], ignore_index=True)
                df_final.to_excel(REPORTE_PATH, index=False)
            else:
                df_nuevo.to_excel(REPORTE_PATH, index=False)
            print("✅ Registro guardado en:", REPORTE_PATH)
        except Exception as e:
            print(f"❌ Error Excel: {e}")

    def generar_correo_manual():
        try:
            hay_faltantes = len(state["faltantes"]) > 0
            titulo_estado = "CON FALTANTES" if hay_faltantes else "OK"
            asunto = f"Reporte {titulo_estado}: BOX {state['box_calculado']} - {state['modelo']}"
            cuerpo = f"""Hola,
            
Reporte de verificacion:

USUARIO: {state['usuario']}
MODELO: {state['modelo']}
BOX: {state['box_calculado']}
ESTADO: {titulo_estado}

FALTANTES: {', '.join(state['faltantes']) if hay_faltantes else 'Ninguno'}

(El usuario debe adjuntar las fotos y el archivo Reporte_Escaneos.xlsx guardado en: {REPORTE_PATH})
"""
            asunto_cod = urllib.parse.quote(asunto)
            cuerpo_cod = urllib.parse.quote(cuerpo)
            mailto_link = f"mailto:?subject={asunto_cod}&body={cuerpo_cod}"
            webbrowser.open(mailto_link)
            return True, "Abriendo cliente de correo..."
        except Exception as e:
            return False, f"Error: {e}"

    def obtener_usuarios():
        try:
            if not os.path.exists(USUARIOS_PATH): return ["LocalUser"]
            df = pd.read_excel(USUARIOS_PATH, header=0)
            return df.iloc[:, 0].dropna().astype(str).tolist()
        except: return ["LocalUser"]

    def obtener_modelos():
        try:
            if not os.path.exists(DB_PATH): return []
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT ModeloCamion FROM piezas ORDER BY ModeloCamion")
            res = [row[0] for row in cur.fetchall()]
            conn.close()
            return res
        except: return []

    def limpiar_rutas_locales():
        state["piezas_teoricas"] = []
        state["piezas_escaneadas"] = []
        state["faltantes"] = []
        state["semana_full"] = ""
        state["box_calculado"] = ""
        state["ruta_foto_box"] = None
        state["ruta_foto_lista"] = None

    # ==========================================
    # PANTALLA 1: LOGIN
    # ==========================================
    def mostrar_login():
        page.clean()
        page.route = "/login"
        
        img_logo = ft.Image(src="logo_ceva.png", width=150, error_content=ft.Text("Logo CEVA"))
        img_camiones = ft.Image(src="foto_camiones.jpg", width=400, height=180, fit="cover")
        img_vw = ft.Image(src="logo_vw.png", width=70)

        dd_usuario = ft.Dropdown(label="Usuario", options=[ft.dropdown.Option(u) for u in obtener_usuarios()], border_color=COLOR_AZUL_CEVA, width=300)
        dd_modelo = ft.Dropdown(label="Modelo", options=[ft.dropdown.Option(m) for m in obtener_modelos()], border_color=COLOR_AZUL_CEVA, width=300)

        def ir_listado(e):
            if not dd_usuario.value or not dd_modelo.value:
                page.snack_bar = ft.SnackBar(ft.Text("Seleccione Usuario y Modelo"), bgcolor=COLOR_ROJO_CEVA)
                page.snack_bar.open = True
                page.update()
                return
            state["usuario"] = dd_usuario.value
            state["modelo"] = dd_modelo.value
            limpiar_rutas_locales()
            mostrar_listado()

        btn_ingresar = ft.ElevatedButton("Ingresar", bgcolor=COLOR_AZUL_CEVA, color="white", width=200, height=50, on_click=ir_listado)

        page.add(ft.Column([
            ft.Container(content=img_logo, alignment=ft.Alignment(0,0), padding=10),
            img_camiones,
            ft.Container(content=img_vw, alignment=ft.Alignment(0,0), padding=10),
            ft.Text("Modo 100% Offline (Local)", weight="bold", size=14, color="grey"),
            ft.Container(height=10),
            dd_usuario, 
            dd_modelo,
            ft.Container(height=20),
            btn_ingresar,
            ft.Container(height=20),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER))

    # ==========================================
    # PANTALLA 2: LISTADO (SETUP)
    # ==========================================
    def mostrar_listado():
        page.clean()
        page.route = "/listado"

        def tomar_foto_box(e):
            page.data = "BOX"
            file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)

        def tomar_foto_lista(e):
            page.data = "LISTA"
            file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)

        txt_semana = ft.TextField(label="Semana (QR)", height=60, text_size=16, autofocus=True, value=state["semana_full"])
        txt_box_display = ft.TextField(label="BOX DETECTADO", read_only=True, bgcolor=ft.Colors.GREY_100, border_color="grey")
        
        lbl_cant = ft.Text("0", size=30, weight="bold", color="white")
        btn_go = ft.ElevatedButton("Comenzar Verificación", bgcolor=COLOR_ROJO_CEVA, color="white", width=300, height=60, disabled=True)

        def check_box(e):
            val = txt_semana.value
            if val and len(val) >= 3:
                box = normalizar_texto(val[:3])
                txt_box_display.value = box
                state["box_calculado"] = box
                
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("SELECT BOX, Material, Medio FROM piezas WHERE ModeloCamion = ? AND BOX = ?", (state["modelo"], box))
                    datos = cur.fetchall()
                    conn.close()
                    
                    state["piezas_teoricas"] = datos
                    lbl_cant.value = str(len(datos))
                    
                    if datos:
                        txt_box_display.border_color = COLOR_VERDE_OK
                        btn_go.disabled = False
                        btn_go.bgcolor = COLOR_VERDE_OK
                    else:
                        txt_box_display.border_color = COLOR_ROJO_CEVA
                        btn_go.disabled = True
                        btn_go.bgcolor = COLOR_ROJO_CEVA
                except Exception as ex:
                    lbl_cant.value = "Err"
                    page.snack_bar = ft.SnackBar(ft.Text(f"Error DB: {ex}"), bgcolor=COLOR_ROJO_CEVA)
                    page.snack_bar.open = True
            else:
                txt_box_display.value = ""
                btn_go.disabled = True
            page.update()

        txt_semana.on_change = check_box

        def ir_val(e):
            state["semana_full"] = txt_semana.value
            state["codigo_unico"] = f"{state['box_calculado']}-{datetime.now().strftime('%Y%m%d%H%M')}"
            mostrar_validacion()

        btn_go.on_click = ir_val

        color_btn_box = COLOR_VERDE_OK if state["ruta_foto_box"] else "white"
        color_txt_box = "white" if state["ruta_foto_box"] else "black"
        color_btn_lista = COLOR_VERDE_OK if state["ruta_foto_lista"] else "white"
        color_txt_lista = "white" if state["ruta_foto_lista"] else "black"

        btn_fotos = ft.Row([
            ft.ElevatedButton("Foto BOX", icon=ft.icons.CAMERA_ALT, bgcolor=color_btn_box, color=color_txt_box, on_click=tomar_foto_box),
            ft.ElevatedButton("Foto Lista", icon=ft.icons.CAMERA_ALT, bgcolor=color_btn_lista, color=color_txt_lista, on_click=tomar_foto_lista)
        ], alignment=ft.MainAxisAlignment.SPACE_EVENLY)

        if state["semana_full"]: check_box(None)

        page.add(ft.Container(padding=15, expand=True, content=ft.Column([
            ft.Container(content=ft.Column([
                ft.Text("Tipo de Camión", color="white", size=12),
                ft.Text(state["modelo"], color="white", weight="bold", size=18)
            ], horizontal_alignment="center"), bgcolor=COLOR_AZUL_CEVA, padding=10, border_radius=8, width=float('inf')),
            ft.Container(height=10),
            txt_semana, 
            txt_box_display,
            ft.Divider(), 
            btn_fotos, 
            ft.Container(height=10),
            ft.Container(content=ft.Row([
                ft.Text("Piezas Totales:", color="white", size=16), 
                lbl_cant
            ], alignment="spaceBetween"), bgcolor=COLOR_AZUL_CEVA, padding=15, border_radius=8),
            ft.Container(height=10),
            btn_go,
            ft.ElevatedButton("Volver", on_click=lambda _: mostrar_login(), color="grey", bgcolor="transparent", elevation=0)
        ], horizontal_alignment="center", scroll="auto")))

    # ==========================================
    # PANTALLA 3: VALIDACIÓN (CORE)
    # ==========================================
    def mostrar_validacion():
        page.clean()
        page.route = "/validacion"
        
        txt_pieza = ft.TextField(label="1. Escanear Pieza", border_color=COLOR_AZUL_CEVA, expand=True, autofocus=True, text_size=18, capitalizations=ft.TextCapitalization.CHARACTERS)
        btn_reset_pieza = ft.IconButton(icon=ft.icons.CLEAR, icon_color="white", bgcolor=COLOR_ROJO_CEVA)

        lbl_destino = ft.Text("ESCANEAR PIEZA PARA COMENZAR", color="white", weight="bold", size=18, text_align="center")
        cont_destino = ft.Container(content=lbl_destino, bgcolor=COLOR_AZUL_CEVA, padding=20, alignment=ft.Alignment(0,0), border_radius=8, width=float('inf'))
        
        txt_carro = ft.TextField(label="2. Confirmar Carro/Medio", border_color=COLOR_AZUL_CEVA, expand=True, text_size=18, disabled=True, capitalizations=ft.TextCapitalization.CHARACTERS)
        btn_reset_carro = ft.IconButton(icon=ft.icons.CLEAR, icon_color="white", bgcolor=COLOR_ROJO_CEVA)

        lbl_res = ft.Text("", weight="bold", size=14, text_align="center")

        def resetear_interfaz(msg="", icon_color="transparent"):
            txt_pieza.value = ""
            txt_carro.value = ""
            txt_pieza.disabled = False
            txt_carro.disabled = True
            lbl_destino.value = "Escanear siguiente pieza"
            cont_destino.bgcolor = COLOR_AZUL_CEVA
            lbl_res.value = msg
            lbl_res.color = icon_color
            page.update()
            try: txt_pieza.focus()
            except: pass

        def al_escanear_pieza(e):
            pieza_in = normalizar_texto(txt_pieza.value)
            txt_pieza.value = pieza_in
            if not pieza_in: return 

            encontrada = False
            medio_asignado = ""
            
            for p in state["piezas_teoricas"]:
                mat_norm = normalizar_texto(p[1])
                if mat_norm == pieza_in:
                    encontrada = True
                    medio_asignado = p[2]
                    break
            
            if encontrada:
                state["medio_esperado_actual"] = medio_asignado
                lbl_destino.value = f"COLOCAR EN:\n{str(medio_asignado).upper()}"
                cont_destino.bgcolor = COLOR_VERDE_OK
                lbl_res.value = ""
            else:
                state["medio_esperado_actual"] = "NOLISTADO"
                lbl_destino.value = "⚠️ PIEZA NO LISTADA ⚠️"
                cont_destino.bgcolor = COLOR_NARANJA_WARN
                lbl_res.value = "Falta confirmar carro (No Listado)."
                lbl_res.color = COLOR_NARANJA_WARN
                
            txt_carro.disabled = False
            txt_pieza.disabled = True 
            page.update()
            try: txt_carro.focus()
            except: pass

        def al_escanear_carro(e):
            carro_in = normalizar_texto(txt_carro.value)
            txt_carro.value = carro_in
            pieza_in = normalizar_texto(txt_pieza.value)
            
            esperado_raw = state["medio_esperado_actual"]
            esperado_norm = normalizar_texto(esperado_raw)
            
            resultado = ""
            msg = ""
            color = ""
            
            if esperado_raw == "NOLISTADO":
                resultado = "NO LISTADO"
                msg = f"REGISTRADO {pieza_in}: NO LISTADO"
                color = COLOR_NARANJA_WARN
                state["faltantes"].append(pieza_in)
            elif esperado_norm == carro_in:
                resultado = "OK"
                msg = f"CORRECTO (OK): {pieza_in}"
                color = COLOR_VERDE_OK
                state["piezas_escaneadas"].append(pieza_in)
            else:
                lbl_res.value = f"❌ ERROR\nESPERADO: {esperado_raw}"
                lbl_res.color = COLOR_ROJO_CEVA
                txt_carro.value = ""
                txt_carro.border_color = COLOR_ROJO_CEVA
                cont_destino.bgcolor = COLOR_ROJO_CEVA
                page.update()
                try: txt_carro.focus()
                except: pass
                
                guardar_registro_excel({
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Usuario": state["usuario"],
                    "Modelo": state["modelo"],
                    "Box": state["box_calculado"],
                    "Pieza": pieza_in,
                    "CarroEscaneado": carro_in,
                    "Resultado": "ERROR_CARRO",
                    "Req ID": state["codigo_unico"]
                })
                return 

            guardar_registro_excel({
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Usuario": state["usuario"],
                "Modelo": state["modelo"],
                "Box": state["box_calculado"],
                "Pieza": pieza_in,
                "CarroEscaneado": carro_in,
                "Resultado": resultado,
                "Req ID": state["codigo_unico"]
            })
            
            txt_carro.border_color = COLOR_AZUL_CEVA
            resetear_interfaz(msg, color)

        txt_pieza.on_submit = al_escanear_pieza
        txt_carro.on_submit = al_escanear_carro
        
        btn_reset_pieza.on_click = lambda _: resetear_interfaz("", "transparent")
        def borrar_carro(e):
            txt_carro.value = ""
            page.update()
            try: txt_carro.focus()
            except: pass
        btn_reset_carro.on_click = borrar_carro

        btn_resumen = ft.ElevatedButton("Finalizar / Resumen", bgcolor=COLOR_AZUL_CEVA, color="white", height=50, expand=True, on_click=lambda _: mostrar_resumen())

        page.add(ft.Container(padding=15, expand=True, content=ft.Column([
            ft.Container(content=ft.Row([
                ft.Text(state["modelo"], color="white", weight="bold"),
                ft.Text(f"BOX: {state['box_calculado']}", color="white", weight="bold")
            ], alignment="spaceBetween"), bgcolor=COLOR_AZUL_CEVA, padding=10, border_radius=8),
            
            ft.Container(height=10),
            ft.Row([txt_pieza, btn_reset_pieza], vertical_alignment="center"),
            
            ft.Container(height=5),
            cont_destino, 
            
            ft.Container(height=5),
            ft.Row([txt_carro, btn_reset_carro], vertical_alignment="center"),
            
            ft.Container(height=10),
            ft.Container(content=lbl_res, alignment=ft.Alignment(0,0), height=50),
            
            ft.Divider(),
            ft.Row([btn_resumen])
        ], scroll="auto")))

    # ==========================================
    # PANTALLA 4: RESUMEN
    # ==========================================
    def mostrar_resumen():
        page.clean()
        page.route = "/resumen"
        
        tot_teo = len(state["piezas_teoricas"])
        tot_esc = len(set(state["piezas_escaneadas"])) 
        
        teoricas_norm = [normalizar_texto(p[1]) for p in state["piezas_teoricas"]]
        escaneadas_norm = [normalizar_texto(p) for p in state["piezas_escaneadas"]]
        
        pendientes_mostrar = []
        for i, teo in enumerate(teoricas_norm):
            if teo not in escaneadas_norm:
                pendientes_mostrar.append(state["piezas_teoricas"][i][1])

        col_faltantes = ft.Column(scroll="auto", expand=True)
        if not pendientes_mostrar:
            col_faltantes.controls.append(ft.Text("¡Ningún faltante! Todo OK.", color=COLOR_VERDE_OK, weight="bold"))
            state["faltantes"] = []
        else:
            state["faltantes"] = pendientes_mostrar
            for f in pendientes_mostrar:
                col_faltantes.controls.append(ft.Text(f"Falta: {f}", size=14, color=COLOR_ROJO_CEVA))

        def enviar_mail_click(e):
            ok, msg = generar_correo_manual()
            page.snack_bar = ft.SnackBar(ft.Text(msg))
            page.snack_bar.open = True
            page.update()

        def cerrar_ok(e):
            guardar_registro_excel({
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Usuario": state["usuario"],
                "Modelo": state["modelo"],
                "Box": state["box_calculado"],
                "Pieza": "CIERRE",
                "CarroEscaneado": "CIERRE",
                "Resultado": "PROCESO FINALIZADO",
                "Req ID": state["codigo_unico"]
            })
            page.snack_bar = ft.SnackBar(ft.Text("Finalizado Correctamente", color="white"), bgcolor=COLOR_VERDE_OK)
            page.snack_bar.open = True
            limpiar_rutas_locales()
            mostrar_login()

        btn_enviar = ft.ElevatedButton("Enviar Correo", icon=ft.icons.MAIL, bgcolor="#4472C4", color="white", height=50, expand=True, on_click=enviar_mail_click)
        btn_ok = ft.ElevatedButton("VERIFICAR OK / CERRAR", icon=ft.icons.CHECK_CIRCLE, bgcolor=COLOR_AZUL_CEVA, color="white", height=50, expand=True, on_click=cerrar_ok)

        page.add(ft.Container(padding=20, expand=True, content=ft.Column([
            ft.Text(f"Resumen: {state['modelo']} - BOX {state['box_calculado']}", size=20, weight="bold", color=COLOR_AZUL_CEVA),
            ft.Container(content=ft.Row([
                ft.Column([
                    ft.Text("Teóricas", size=14, color="grey"),
                    ft.Text(str(tot_teo), size=24, weight="bold")
                ], horizontal_alignment="center", expand=True),
                ft.Container(width=1, bgcolor="grey", height=50),
                ft.Column([
                    ft.Text("Escaneadas", size=14, color="grey"),
                    ft.Text(str(tot_esc), size=24, weight="bold", color=COLOR_VERDE_OK if tot_esc >= tot_teo else "black")
                ], horizontal_alignment="center", expand=True)
            ]), padding=10, border_radius=8, bgcolor=ft.Colors.GREY_100),
            
            ft.Divider(),
            ft.Text("PIEZAS SIN ESCANEAR (FALTANTES):", weight="bold", size=14, color=COLOR_NARANJA_WARN),
            ft.Container(content=col_faltantes, border=ft.border.all(1, "grey"), border_radius=8, padding=10, expand=True),
            
            ft.Divider(),
            ft.Row([btn_enviar], alignment="center"),
            ft.Container(height=5),
            ft.Row([btn_ok], alignment="center")
        ])))

    mostrar_login()

ft.app(target=main, assets_dir="assets")
