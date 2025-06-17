import pyodbc
import pandas as pd
from fpdf import FPDF
from openai import OpenAI
from datetime import datetime, timedelta

# === 1. CONFIGURACIÓN ===

# Conexión a la base de datos
def conectar_bd():
    try:
        conn = pyodbc.connect(
            'DRIVER={SQL Server};SERVER=DESKTOP-J8TVKPT,1433;DATABASE=BaseDatosTFG;Trusted_Connection=yes;',
            timeout=10
        )
        print("✅ Conexión exitosa")
        return conn
    except Exception as e:
        print(f"❌ Error al conectar: {e}")
        return None

# Clave API
client = OpenAI(api_key='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')
# === 2. CONSULTA DE DATOS POR PACIENTE Y SEMANA ===

# ---------- 1. DATOS DEL PACIENTE ----------
def obtener_datos_paciente(conn, id_pa, fecha_inicio, fecha_fin):
    query = """
    SELECT 
        pa.id_pa,
        pa.nombre AS nombre_paciente,
        MIN(re.date) AS fecha_inicio,
        MAX(re.date) AS fecha_fin,
        pat.nombre AS tipo_tratamiento
    FROM paciente pa
    JOIN link_paciente_patologia_rb lpp ON pa.id_pa = lpp.id_pa
    JOIN patologia_rb pat ON lpp.id_pat = pat.id_pat
    JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
    JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
    WHERE pa.id_pa = ? AND TRY_CAST(re.date AS DATE) BETWEEN ? AND ?
    GROUP BY pa.id_pa, pa.nombre, pat.nombre;
    """
    return pd.read_sql(query, conn, params=[id_pa, fecha_inicio, fecha_fin])



# ---------- 2. ADHERENCIA Y DATOS SEMANALES ----------
def obtener_adherencia_semanal(conn, id_pa, fecha_inicio, fecha_fin):
    query = f"""
    WITH dias_totales AS (
        SELECT 
            pa.id_pa,
            DATEADD(DAY, v.n, ?) AS fecha
        FROM paciente pa
        CROSS JOIN (SELECT TOP (21) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) - 1 AS n FROM sys.all_objects) v
        WHERE pa.id_pa = {id_pa}
    ),
    resultados_diarios AS (
        SELECT
            pa.id_pa,
            CAST(re.date AS DATE) AS fecha,
            COUNT(DISTINCT re.id_linkpaej) AS ejercicios_realizados,
            IIF(SUM(CAST(re.valor AS FLOAT)) > 0, 1, 0) AS sesion_completa,
            AVG(CAST(re.valor AS FLOAT)) AS adherencia_diaria
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
        WHERE pa.id_pa = ? AND re.date BETWEEN ? AND ?
        GROUP BY pa.id_pa, CAST(re.date AS DATE)
    ),
    fechas_completas AS (
        SELECT 
            dt.id_pa,
            dt.fecha,
            ISNULL(rd.ejercicios_realizados, 0) AS ejercicios_realizados,
            ISNULL(rd.sesion_completa, 0) AS sesion_completa,
            ISNULL(rd.adherencia_diaria, 0) AS adherencia_diaria,
            'Semana ' + CAST(DATEDIFF(WEEK, ?, dt.fecha) + 1 AS VARCHAR) AS semana
        FROM dias_totales dt
        LEFT JOIN resultados_diarios rd ON dt.fecha = rd.fecha AND dt.id_pa = rd.id_pa
    ),
    resumen_semanal AS (
        SELECT 
            id_pa,
            semana,
            COUNT(*) AS dias_programados,
            SUM(sesion_completa) AS sesiones_realizadas,
            SUM(ejercicios_realizados) AS total_ejercicios,
            ROUND(SUM(adherencia_diaria) / 5.0, 2) AS adherencia_pct
        FROM fechas_completas
        GROUP BY id_pa, semana
    ),
    dias_sin_actividad AS (
        SELECT 
            id_pa,
            fecha,
            semana
        FROM fechas_completas
        WHERE ejercicios_realizados = 0
    )
    SELECT 
        r.id_pa,
        r.semana,
        r.sesiones_realizadas,
        r.dias_programados,
        r.total_ejercicios,
        r.adherencia_pct,
        STRING_AGG(CONVERT(VARCHAR, d.fecha, 23), ', ') AS fechas_sin_actividad
    FROM resumen_semanal r
    LEFT JOIN dias_sin_actividad d ON r.id_pa = d.id_pa AND r.semana = d.semana
    GROUP BY 
        r.id_pa, r.semana, r.sesiones_realizadas, r.dias_programados, r.total_ejercicios, r.adherencia_pct
    ORDER BY r.semana;
    """
    return pd.read_sql(query, conn, params=[fecha_inicio, id_pa, fecha_inicio, fecha_fin, fecha_inicio])



# ---------- 3. EVOLUCIÓN DE MOVIMIENTO ----------
def obtener_evolucion_movimiento(conn, id_pa, fecha_inicio, fecha_fin):

    query = f"""
    WITH rom_semana AS (
        SELECT 
            pa.id_pa,
            DATEPART(WEEK, CAST(re.date AS datetime)) AS semana,

            -- Promedios semanales combinando lados A y B
            ROUND(AVG(
                (CAST(mo.romTopA AS FLOAT) + CAST(mo.romTopB AS FLOAT)) / 2.0
            ), 2) AS romTop_avg,

            ROUND(AVG(
                (CAST(mo.romBotA AS FLOAT) + CAST(mo.romBotB AS FLOAT)) / 2.0
            ), 2) AS romBot_avg,

            ROUND(AVG(
                (CAST(mo.avgTopA AS FLOAT) + CAST(mo.avgTopB AS FLOAT)) / 2.0
            ), 2) AS avgTop_avg,

            ROUND(AVG(
                (CAST(mo.avgBotA AS FLOAT) + CAST(mo.avgBotB AS FLOAT)) / 2.0
            ), 2) AS avgBot_avg,

            -- Coeficiente de Calidad del Movimiento (CQ)
            ROUND(
                (
                    AVG((CAST(mo.avgTopA AS FLOAT) + CAST(mo.avgTopB AS FLOAT)) / 2.0) -
                    AVG((CAST(mo.avgBotA AS FLOAT) + CAST(mo.avgBotB AS FLOAT)) / 2.0)
                ) /
                NULLIF(
                    AVG((CAST(mo.romTopA AS FLOAT) + CAST(mo.romTopB AS FLOAT)) / 2.0) -
                    AVG((CAST(mo.romBotA AS FLOAT) + CAST(mo.romBotB AS FLOAT)) / 2.0),
                    0
                ) * 100, 
            2) AS CQ 

        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
        JOIN movimiento_rb mo ON mo.id_re = re.id_re
        WHERE ISDATE(re.date) = 1
            AND pa.id_pa = ?
            AND CAST(re.date AS datetime) BETWEEN ? AND ?
        GROUP BY pa.id_pa, DATEPART(WEEK, CAST(re.date AS datetime))
    )

    SELECT 
        *,
        -- Variaciones semana a semana
        ROUND(CQ - LAG(CQ) OVER (PARTITION BY id_pa ORDER BY semana), 2) AS CQ_var
    FROM rom_semana
    ORDER BY semana;


    """
    return pd.read_sql(query, conn, params=[id_pa, fecha_inicio, fecha_fin])


# ---------- 4. EVOLUCIÓN DEL DOLOR Y ANSIEDAD ----------
def obtener_evolucion_dolor(conn, id_pa: int, fecha_inicio, fecha_fin) -> pd.DataFrame:
    query = f"""
    SELECT 
        DATEPART(week, CONVERT(date, l.date, 103)) AS semana,
        YEAR(CONVERT(date, l.date, 103)) AS anio,
        AVG(CAST(l.punt1 AS FLOAT)) AS dolor_promedio
    FROM link_fisio_paciente_escala l
    WHERE 
        l.id_pa = ?
        AND l.id_es = 9
        AND CONVERT(date, l.date, 103) BETWEEN ? AND ?
    GROUP BY 
        DATEPART(week, CONVERT(date, l.date, 103)),
        YEAR(CONVERT(date, l.date, 103))
    ORDER BY anio, semana;
    """
    return pd.read_sql(query, conn, params=[id_pa, fecha_inicio, fecha_fin])


def obtener_evolucion_ansiedad(conn, id_pa: int, fecha_inicio, fecha_fin) -> pd.DataFrame:
    query = """
    SELECT 
        DATEPART(week, CONVERT(date, l.date, 103)) AS semana,
        YEAR(CONVERT(date, l.date, 103)) AS anio,
        AVG(CAST(l.punt1 AS FLOAT)) AS ansiedad_promedio
    FROM link_fisio_paciente_escala l
    WHERE 
        l.id_pa = ?
        AND l.id_es = 12
        AND CONVERT(date, l.date, 103) BETWEEN ? AND ?
    GROUP BY 
        DATEPART(week, CONVERT(date, l.date, 103)),
        YEAR(CONVERT(date, l.date, 103))
    ORDER BY anio, semana;
    """
    return pd.read_sql(query, conn, params=[id_pa, fecha_inicio, fecha_fin])


def construir_prompt_completo(id_pa, datos_paciente, adherencia, movimiento, dolor, ansiedad):
    nombre = datos_paciente["nombre_paciente"].iloc[0]
    patologia = datos_paciente["tipo_tratamiento"].iloc[0]
    fecha_inicio = datos_paciente["fecha_inicio"].iloc[0].date()
    fecha_fin = datos_paciente["fecha_fin"].iloc[0].date()

    prompt = f"""
Estructura del Informe para Especialistas (Evaluación Individual del Programa Preventivo)

**RESUMEN**
- Análisis general de la evolución del paciente durante el periodo cubierto.
- Identificación de mejoras, estancamientos o retrocesos relevantes.
- Alertas de bajo rendimiento: por ejemplo, adherencia baja o síntomas persistentes.
- Recomendaciones inmediatas si se detecta alguna situación crítica.

**EVOLUCIÓN DE MÉTRICAS**

**1 ADHERENCIA AL PROGRAMA**
Resumen por semana:
"""
    for _, row in adherencia.iterrows():
        prompt += (
            f"- {row['semana']}: {row['sesiones_realizadas']} sesiones completadas de "
            f"{row['dias_programados']} programadas. "
            f"Ejercicios totales: {row['total_ejercicios']}. "
            f"Adherencia: {row['adherencia_pct']}%. "
            f"Fechas sin actividad: {row['fechas_sin_actividad'] or 'Ninguna'}\n"
        )

    prompt += "\n**2 ESTADO DE SALUD**\n"
    for _, row in dolor.iterrows():
        prompt += f"- Dolor promedio en {row['semana']}: {row['dolor_promedio']:.1f}\n"
    for _, row in ansiedad.iterrows():
        prompt += f"- Ansiedad promedio en {row['semana']}: {row['ansiedad_promedio']:.1f}\n"

    prompt += "\n**3 RANGO DE MOVIMIENTO (ROM)**\n"
    for _, row in movimiento.iterrows():
        semana = row["semana"]
        prompt += (
            f"- Semana {semana}: CQ = {row['CQ']}%. "
            f"Variación respecto semana anterior: {row['CQ_var']}%\n"
        )


    prompt += """
**ANÁLISIS DE LOS DATOS**
- Describe tendencias relevantes (mejoras o retrocesos).
- Menciona hallazgos inesperados o inconsistencias.
- Detecta relaciones posibles entre adherencia, dolor y ROM.

**CONCLUSIONES Y PRÓXIMOS PASOS**
- Breve resumen del progreso general del paciente.
- Ajustes sugeridos al tratamiento según los datos.
- Recomendaciones específicas y claras para el paciente.
"""

    return prompt

from datetime import datetime

def generar_informe_paciente(id_pa, fecha_inicio, fecha_fin):
    conn = conectar_bd()
    if not conn:
        return

    # ✅ Asegurarse de que las fechas están en formato texto 'YYYY-MM-DD'
    # y no como datetime.date, para evitar problemas con pyodbc
    fecha_inicio_obj = datetime.strptime(fecha_inicio.strip(), "%Y-%m-%d")
    fecha_fin_obj = datetime.strptime(fecha_fin.strip(), "%Y-%m-%d")

    if fecha_inicio_obj > fecha_fin_obj:
        print("❌ Error: La fecha de inicio no puede ser posterior a la fecha de fin.")
        exit()

    # Obtener datos con fechas parametrizadas
    datos_paciente = obtener_datos_paciente(conn, id_pa, fecha_inicio_obj, fecha_fin_obj)
    adherencia = obtener_adherencia_semanal(conn, id_pa, fecha_inicio_obj, fecha_fin_obj)
    movimiento = obtener_evolucion_movimiento(conn, id_pa, fecha_inicio_obj, fecha_fin_obj)
    dolor = obtener_evolucion_dolor(conn, id_pa, fecha_inicio_obj, fecha_fin_obj)
    ansiedad = obtener_evolucion_ansiedad(conn, id_pa, fecha_inicio_obj, fecha_fin_obj)


    graficos = crear_graficos(id_pa, dolor, adherencia, movimiento)
    prompt = construir_prompt_completo(id_pa, datos_paciente, adherencia, movimiento, dolor, ansiedad)

    informe = generar_informe_gpt(prompt)

    paciente_info = {
        "codigo": id_pa,
        "tratamiento": datos_paciente["tipo_tratamiento"].iloc[0],
        "graficos": graficos
    }
    informe_info = {
        "fecha_informe": datetime.today().strftime('%d/%m/%Y'),
        "periodo_informe": f"{fecha_inicio_obj.date()} al {fecha_fin_obj.date()}",
        "graficos": graficos
    }

    exportar_pdf(informe, f"informe_paciente_{id_pa}.pdf", paciente_info, informe_info)
    conn.close()


# === 5. LLAMADA A GPT ===

def generar_informe_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": "Eres un fisioterapeuta experto redactando informes semanales de evolución de pacientes en programas preventivos."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.7
    )
    return response.choices[0].message.content

# === 6. GENERACION DE GRÁFICOS ===
import matplotlib.pyplot as plt
import os

def crear_graficos(id_pa, dolor_df, adherencia_df, movimiento_df):
    import os
    import matplotlib.pyplot as plt

    carpeta = "graficos_temp"
    os.makedirs(carpeta, exist_ok=True)
    ruta_absoluta = os.path.abspath(carpeta)

    rutas = {}

    # 1. Dolor
    if not dolor_df.empty:
        path = os.path.join(ruta_absoluta, f"dolor_{id_pa}.png")
        plt.figure()
        plt.plot(dolor_df['semana'], dolor_df['dolor_promedio'], marker='o')
        plt.title("Evolución del Dolor Promedio por Semana")
        plt.xlabel("Semana")
        plt.ylabel("Dolor Promedio")
        plt.savefig(path)
        plt.close()
        rutas["dolor"] = path

    # 2. Adherencia
    if not adherencia_df.empty:
        path = os.path.join(ruta_absoluta, f"adherencia_{id_pa}.png")
        plt.figure()
        plt.bar(adherencia_df['semana'], adherencia_df['adherencia_pct'], color='skyblue')
        plt.title("Adherencia Semanal Promedio (%)")
        plt.xlabel("Semana")
        plt.ylabel("Adherencia (%)")
        plt.ylim(0, 100)
        plt.savefig(path)
        plt.close()
        rutas["adherencia"] = path

    # 3. Calidad del Movimiento (CQ)
    if not movimiento_df.empty and 'CQ' in movimiento_df.columns:
        path = os.path.join(ruta_absoluta, f"rom_{id_pa}.png")
        plt.figure()
        plt.plot(movimiento_df['semana'], movimiento_df['CQ'], marker='o', color='purple')
        plt.title("Coeficiente de Calidad del Movimiento (CQ) por semana")
        plt.ylabel("CQ (%)")
        plt.xlabel("Semana")
        plt.ylim(0, 200)  # Por si hay variaciones grandes
        plt.grid(True)
        plt.savefig(path)
        plt.close()
        rutas["rom"] = path


    return rutas




# === 7. EXPORTACIÓN A PDF ===

def exportar_pdf(texto, nombre_archivo, paciente_data, informe_data):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    def agregar_titulo_seccion(pdf, titulo):
        pdf.set_font("Arial", 'B', 13)
        pdf.set_fill_color(0, 70, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, titulo, ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    # Logo
    try:
        pdf.image("Logo-RehBody-07.png", x=10, y=8, w=30)
    except RuntimeError:
        print("⚠️ No se pudo cargar el logo. Asegúrate de que 'Logo-RehBody-07.png' exista.")
    pdf.ln(25)

    # Título
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Informe Médico del paciente", ln=True, align="C")
    pdf.ln(10)

    # Datos principales
    pdf.set_font("Arial", size=12)
    pdf.cell(95, 10, f'Código del paciente: {paciente_data["codigo"]}', ln=0)
    pdf.cell(95, 10, f'Tipo de tratamiento: {paciente_data["tratamiento"]}', ln=1)
    pdf.cell(95, 10, f'Fecha del informe: {informe_data["fecha_informe"]}', ln=0)
    pdf.cell(95, 10, f'Periodo cubierto: {informe_data["periodo_informe"]}', ln=1)
    pdf.ln(10)

    agregar_titulo_seccion(pdf, "RESUMEN Y ANÁLISIS")
    
    # Informe de texto generado
    for linea in texto.split('\n'):
        if linea.strip().startswith("**") and linea.strip().endswith("**"):
            # Si la línea es un título con ** al inicio y final
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, linea.strip("*"), ln=True)
            pdf.set_font("Arial", '', 11)
        else:
            pdf.set_font("Arial", '', 11)
            pdf.multi_cell(0, 8, linea)

    # Gráficos
    if "graficos" in informe_data and isinstance(informe_data["graficos"], dict):
        pdf.add_page()
        agregar_titulo_seccion(pdf, "GRÁFICAS Y MÉTRICAS DEL PROGRAMA")
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Visualización de métricas del programa", ln=True, align="C")
        pdf.ln(5)

        for nombre, ruta in informe_data["graficos"].items():
            if os.path.exists(ruta):
                try:
                    pdf.image(ruta, w=170)
                    pdf.ln(10)
                    print(f"✅ Gráfico '{nombre}' insertado correctamente")
                except RuntimeError as e:
                    print(f"⚠️ Error al insertar gráfico {nombre}: {e}")
            else:
                print(f"⚠️ Ruta no encontrada para gráfico '{nombre}': {ruta}")

    # Guardar
    pdf.output(nombre_archivo)
    print(f"📄 Informe guardado como {nombre_archivo}")


# === 8. EJECUCIÓN PRINCIPAL ===

if __name__ == "__main__":
    try:
        id_input = input("🔎 Introduce el ID del paciente: ").strip()
        if not id_input.isdigit():
            raise ValueError("El ID debe ser un número entero positivo.")
        id_pa = int(id_input)

        fecha_inicio = input("📅 Introduce la fecha de inicio (YYYY-MM-DD): ").strip()
        fecha_fin = input("📅 Introduce la fecha de fin (YYYY-MM-DD): ").strip()

        # Validación básica de fechas
        try:
            datetime.strptime(fecha_inicio, "%Y-%m-%d")
            datetime.strptime(fecha_fin, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Las fechas deben tener formato YYYY-MM-DD válido.")

        generar_informe_paciente(id_pa, fecha_inicio, fecha_fin)

    except ValueError as e:
        print(f"❌ {e}")


