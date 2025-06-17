# === 1. IMPORTACIONES Y CONEXIÓN ===
import pyodbc
import pandas as pd
import matplotlib.pyplot as plt
from fpdf import FPDF
from openai import OpenAI
from datetime import datetime
import os

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

# API Key OpenAI (ajustar aquí)
client = OpenAI(api_key='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')


# === 2. CONSULTAS DE DATOS ===

# ==================================
# 2. CONSULTAS PARA EL INFORME EMPRESA
# ==================================

# 2.1. Número total de empleados evaluados
def numero_total_empleados(conn, fecha_inicio, fecha_fin):
    sql = f"""
    SELECT 
        COUNT(DISTINCT pa.id_pa) AS total_empleados
    FROM paciente pa
    LEFT JOIN link_paciente_ejercicio_rb lpe 
        ON pa.id_pa = lpe.id_pa
    LEFT JOIN resultado_rb re 
        ON re.id_linkpaej = lpe.id_linkpaej
        AND CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    LEFT JOIN link_fisio_paciente_escala lfe 
        ON pa.id_pa = lfe.id_pa
        AND CONVERT(date, lfe.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    WHERE 
        re.id_linkpaej IS NOT NULL
        OR lfe.id_es IS NOT NULL;
    """
    return pd.read_sql(sql, conn)


# 2.2. Número de empleados activos (adherencia >= umbral)
def numero_empleados_activos(conn, fecha_inicio, fecha_fin, umbral_pct=50):
    sql = f"""
    WITH total_sesiones AS (
        SELECT 
            pa.id_pa,
            SUM(lpp.minAdhDias) * DATEDIFF(WEEK, '{fecha_inicio}', '{fecha_fin}') AS sesiones_programadas
        FROM paciente pa
        JOIN link_paciente_patologia_rb lpp 
            ON pa.id_pa = lpp.id_pa
        GROUP BY pa.id_pa
    ),
    sesiones_realizadas AS (
        SELECT 
            pa.id_pa,
            COUNT(DISTINCT CONVERT(date, re.date, 103)) AS dias_hizo
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe 
            ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re 
            ON re.id_linkpaej = lpe.id_linkpaej
        WHERE 
            CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            AND CAST(re.valor AS FLOAT) > 0
        GROUP BY pa.id_pa
    )
    SELECT 
        COUNT(*) AS empleados_activos
    FROM (
        SELECT 
            t.id_pa,
            ROUND(
                CASE 
                    WHEN t.sesiones_programadas > 0 
                        THEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.sesiones_programadas) * 100 
                    ELSE 0 
                END, 2
            ) AS adherencia_pct
        FROM total_sesiones t
        LEFT JOIN sesiones_realizadas r 
            ON t.id_pa = r.id_pa
    ) sub
    WHERE sub.adherencia_pct >= {umbral_pct};
    """
    df = pd.read_sql(sql, conn)
    return df  # DataFrame con una sola fila: empleados_activos


# 2.3. Adherencia general promedio (todos los empleados)
def adherencia_general(conn, fecha_inicio, fecha_fin):
    sql = f"""
    WITH total_paciente AS (
        SELECT 
            pa.id_pa,
            SUM(lpp.minAdhDias) * DATEDIFF(WEEK, '{fecha_inicio}', '{fecha_fin}') AS sesiones_programadas
        FROM paciente pa
        JOIN link_paciente_patologia_rb lpp 
            ON pa.id_pa = lpp.id_pa
        GROUP BY pa.id_pa
    ),
    realizadas_paciente AS (
        SELECT 
            pa.id_pa,
            COUNT(DISTINCT CONVERT(date, re.date, 103)) AS dias_hizo
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe 
            ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re 
            ON re.id_linkpaej = lpe.id_linkpaej
        WHERE 
            CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            AND CAST(re.valor AS FLOAT) > 0
        GROUP BY pa.id_pa
    )
    SELECT 
        ROUND(
            AVG(
                CASE 
                    WHEN t.sesiones_programadas > 0 
                        THEN 
                            CASE 
                                WHEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.sesiones_programadas) * 100 > 100 
                                    THEN 100 
                                ELSE (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.sesiones_programadas) * 100 
                            END
                    ELSE 0 
                END
            ), 2
        ) AS adherencia_promedio
    FROM total_paciente t
    LEFT JOIN realizadas_paciente r 
        ON t.id_pa = r.id_pa;
    """
    return pd.read_sql(sql, conn)


# 2.4. Porcentaje de empleados activos (reutiliza total y activos)
def porcentaje_empleados_activos(conn, fecha_inicio, fecha_fin, umbral_pct=50):
    total = numero_total_empleados(conn, fecha_inicio, fecha_fin).iloc[0,0]
    activos = numero_empleados_activos(conn, fecha_inicio, fecha_fin, umbral_pct).iloc[0,0]
    porcentaje = round((activos / total) * 100, 2) if total > 0 else 0
    return pd.DataFrame({
        "total_empleados": [total],
        "empleados_activos": [activos],
        "porcentaje_activos": [porcentaje]
    })


# 2.5. Porcentaje de finalización de ejercicios (que completaron todos)
def porcentaje_finalizacion_ejercicios(conn, fecha_inicio, fecha_fin):
    sql = f"""
    WITH asignados AS (
        SELECT 
            lpe.id_pa,
            COUNT(DISTINCT lpe.id_linkpaej) AS total_asignados
        FROM link_paciente_ejercicio_rb lpe
        JOIN link_paciente_patologia_rb lpp 
            ON lpe.id_pa = lpp.id_pa
        GROUP BY lpe.id_pa
    ),
    completados AS (
        SELECT 
            pa.id_pa,
            COUNT(DISTINCT lpe.id_linkpaej) AS hechos_completos
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe 
            ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re 
            ON re.id_linkpaej = lpe.id_linkpaej
        WHERE 
            CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            AND CAST(re.valor AS FLOAT) >= 100
        GROUP BY pa.id_pa
    ),
    comparacion AS (
        SELECT 
            a.id_pa,
            CASE 
                WHEN a.total_asignados = ISNULL(c.hechos_completos,0) 
                    THEN 1 ELSE 0 
            END AS completo_all
        FROM asignados a
        LEFT JOIN completados c 
            ON a.id_pa = c.id_pa
    )
    SELECT 
        ROUND((SUM(completo_all) * 100.0) / COUNT(*), 2) AS porcentaje_completaron_todo
    FROM comparacion;
    """
    return pd.read_sql(sql, conn)


# 2.6. Evaluación global estado de salud (promedio de escalas)
def evaluacion_global_estado_salud(conn, fecha_inicio, fecha_fin):
    sql = f"""
    SELECT 
        l.id_es AS id_escala,
        ROUND(AVG(CAST(l.punt1 AS FLOAT)), 2) AS promedio_puntaje
    FROM link_fisio_paciente_escala l
    WHERE 
        CONVERT(date, l.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    GROUP BY l.id_es
    ORDER BY l.id_es;
    """
    df = pd.read_sql(sql, conn)
    nombres = {
        9: "Escala END (Dolor)",
        29: "Escala Ansiedad"
    }
    df["nombre_escala"] = df["id_escala"].map(nombres).fillna("Escala " + df["id_escala"].astype(str))
    return df[["id_escala", "nombre_escala", "promedio_puntaje"]]


# 2.7. Mejora promedio en ROM (promedio de cambio % en ROM entre primera y última semana)
def mejora_promedio_rom(conn, fecha_inicio, fecha_fin):
    sql = f"""
    WITH cq_semanal AS (
        SELECT 
            pa.id_pa,
            DATEPART(WEEK, CONVERT(date, re.date, 103)) AS semana,
            AVG(
                CASE 
                    WHEN TRY_CAST(m.romTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotA AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotA AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopA AS FLOAT) - TRY_CAST(m.avgBotA AS FLOAT)) / (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT))) * 100

                    WHEN TRY_CAST(m.romTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotB AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotB AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopB AS FLOAT) - TRY_CAST(m.avgBotB AS FLOAT)) / (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT))) * 100
                    ELSE NULL
                END
            ) AS cq_promedio
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
        JOIN movimiento_rb m ON m.id_re = re.id_re
        WHERE CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
        GROUP BY pa.id_pa, DATEPART(WEEK, CONVERT(date, re.date, 103))
    ), extremos AS (
        SELECT id_pa, MIN(semana) AS ini, MAX(semana) AS fin FROM cq_semanal GROUP BY id_pa
    ), cmp AS (
        SELECT c1.id_pa, c1.cq_promedio AS cq_ini, c2.cq_promedio AS cq_fin,
               ((c2.cq_promedio - c1.cq_promedio) / NULLIF(c1.cq_promedio, 0)) * 100 AS pct_cambio
        FROM cq_semanal c1
        JOIN cq_semanal c2 ON c1.id_pa = c2.id_pa
        JOIN extremos e ON e.id_pa = c1.id_pa
        WHERE c1.semana = e.ini AND c2.semana = e.fin
    )
    SELECT ROUND(AVG(pct_cambio), 2) AS mejora_rom_pct FROM cmp;
    """
    return pd.read_sql(sql, conn)


# 2.8. Evolución de adherencia por semana (cap en 100%)
def evolucion_adherencia_tiempo(conn, fecha_inicio, fecha_fin):
    sql = f"""
    WITH por_semana AS (
        SELECT 
            DATEPART(WEEK, CONVERT(date, re.date, 103)) AS periodo,
            lpp.minAdhDias,
            COUNT(DISTINCT CONVERT(date, re.date, 103)) AS dias_hizo
        FROM paciente pa
        JOIN link_paciente_patologia_rb lpp 
            ON pa.id_pa = lpp.id_pa
        JOIN link_paciente_ejercicio_rb lpe 
            ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re 
            ON re.id_linkpaej = lpe.id_linkpaej
        WHERE 
            CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            AND CAST(re.valor AS FLOAT) > 0
        GROUP BY DATEPART(WEEK, CONVERT(date, re.date, 103)), lpp.minAdhDias
    )
    SELECT 
        periodo,
        ROUND(
            AVG(
                CASE 
                    WHEN minAdhDias > 0 
                        THEN 
                            CASE 
                                WHEN (dias_hizo * 100.0) / minAdhDias > 100 
                                    THEN 100 
                                ELSE (dias_hizo * 100.0) / minAdhDias 
                            END
                    ELSE 0 
                END
            ), 2
        ) AS adherencia_periodo_pct
    FROM por_semana
    GROUP BY periodo
    ORDER BY periodo;
    """
    return pd.read_sql(sql, conn)


# 2.9. Evolución de salud (dolor y ansiedad) por semana
def evolucion_estado_salud_global(conn, fecha_inicio, fecha_fin, id_escala):
    sql = f"""
    SELECT 
        DATEPART(WEEK, CONVERT(date, l.date, 103)) AS periodo,
        YEAR(CONVERT(date, l.date, 103)) AS anio,
        ROUND(AVG(CAST(l.punt1 AS FLOAT)), 2) AS promedio_puntaje
    FROM link_fisio_paciente_escala l
    WHERE 
        l.id_es = {id_escala}
        AND CONVERT(date, l.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    GROUP BY 
        DATEPART(WEEK, CONVERT(date, l.date, 103)),
        YEAR(CONVERT(date, l.date, 103))
    ORDER BY anio, periodo;
    """
    return pd.read_sql(sql, conn)


# 2.10. Evolución de ROM promedio global por semana (para gráfica interpretativa)
def evolucion_rom_global(conn, fecha_inicio, fecha_fin):
    sql = f"""
    WITH cq_semanal AS (
        SELECT 
            DATEPART(WEEK, CONVERT(date, re.date, 103)) AS semana,
            AVG(
                CASE 
                    WHEN TRY_CAST(m.romTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotA AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotA AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopA AS FLOAT) - TRY_CAST(m.avgBotA AS FLOAT)) / (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT))) * 100

                    WHEN TRY_CAST(m.romTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotB AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotB AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopB AS FLOAT) - TRY_CAST(m.avgBotB AS FLOAT)) / (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT))) * 100
                    ELSE NULL
                END
            ) AS cq_prom
        FROM resultado_rb re
        JOIN movimiento_rb m ON m.id_re = re.id_re
        WHERE CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
        GROUP BY DATEPART(WEEK, CONVERT(date, re.date, 103))
    )
    SELECT semana AS periodo, ROUND(cq_prom, 2) AS rom_prom FROM cq_semanal ORDER BY semana;
    """
    return pd.read_sql(sql, conn)


# 2.11. Alertas de bajo desempeño (adherencia < umbral o mejora ROM < umbral)
def alertas_bajo_desempeno(conn, fecha_inicio, fecha_fin, umbral_adherencia=50, umbral_rom_pct=10):
    # Empleados con adherencia baja
    sql_ad = f"""
    WITH tot AS (
        SELECT 
            pa.id_pa,
            SUM(lpp.minAdhDias) * DATEDIFF(WEEK, '{fecha_inicio}', '{fecha_fin}') AS programadas
        FROM paciente pa
        JOIN link_paciente_patologia_rb lpp ON pa.id_pa = lpp.id_pa
        GROUP BY pa.id_pa
    ),
    real AS (
        SELECT 
            pa.id_pa,
            COUNT(DISTINCT CONVERT(date, re.date, 103)) AS dias_hizo
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
        WHERE CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
              AND CAST(re.valor AS FLOAT) > 0
        GROUP BY pa.id_pa
    )
    SELECT 
        t.id_pa,
        ROUND(
            CASE 
                WHEN t.programadas > 0 
                    THEN 
                        CASE 
                            WHEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 > 100 
                                THEN 100 
                            ELSE (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 
                        END
                ELSE 0 END
        , 2) AS adherencia_pct
    FROM tot t
    LEFT JOIN real r ON t.id_pa = r.id_pa
    WHERE 
        ROUND(
            CASE 
                WHEN t.programadas > 0 
                    THEN 
                        CASE 
                            WHEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 > 100 
                                THEN 100 
                            ELSE (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 
                        END
                ELSE 0 END
        , 2) < {umbral_adherencia};
    """
    df_ad_baja = pd.read_sql(sql_ad, conn)

    # Empleados con baja mejora de calidad de movimiento (CQ)
    sql_rom = f"""
    WITH cq_semanal AS (
        SELECT 
            pa.id_pa,
            DATEPART(WEEK, CONVERT(date, re.date, 103)) AS semana,
            AVG(
                CASE 
                    WHEN TRY_CAST(m.romTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotA AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopA AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotA AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopA AS FLOAT) - TRY_CAST(m.avgBotA AS FLOAT)) / (TRY_CAST(m.romTopA AS FLOAT) - TRY_CAST(m.romBotA AS FLOAT))) * 100

                    WHEN TRY_CAST(m.romTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.romBotB AS FLOAT) IS NOT NULL
                         AND TRY_CAST(m.avgTopB AS FLOAT) IS NOT NULL AND TRY_CAST(m.avgBotB AS FLOAT) IS NOT NULL
                         AND (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT)) != 0
                    THEN ((TRY_CAST(m.avgTopB AS FLOAT) - TRY_CAST(m.avgBotB AS FLOAT)) / (TRY_CAST(m.romTopB AS FLOAT) - TRY_CAST(m.romBotB AS FLOAT))) * 100
                    ELSE NULL
                END
            ) AS cq
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re ON re.id_linkpaej = lpe.id_linkpaej
        JOIN movimiento_rb m ON m.id_re = re.id_re
        WHERE CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
        GROUP BY pa.id_pa, DATEPART(WEEK, CONVERT(date, re.date, 103))
    ), extremos AS (
        SELECT id_pa, MIN(semana) AS ini, MAX(semana) AS fin FROM cq_semanal GROUP BY id_pa
    ), cmp AS (
        SELECT c1.id_pa, ((c2.cq - c1.cq) / NULLIF(c1.cq, 0)) * 100 AS pct_cambio
        FROM cq_semanal c1
        JOIN cq_semanal c2 ON c1.id_pa = c2.id_pa
        JOIN extremos e ON e.id_pa = c1.id_pa
        WHERE c1.semana = e.ini AND c2.semana = e.fin
    )
    SELECT id_pa, ROUND(pct_cambio, 2) AS rom_pct_cambio FROM cmp WHERE ROUND(pct_cambio, 2) < {umbral_rom_pct};
    """
    df_rom_baja = pd.read_sql(sql_rom, conn)

    return df_ad_baja, df_rom_baja



# 2.12. Áreas críticas (Top 3 ejercicios peor cumplidos)
def areas_criticas_necesitan_atencion(conn, fecha_inicio, fecha_fin):
    sql_ej = f"""
    SELECT 
        ej.id_ej,
        ej.nombre AS nombre_ejercicio,
        ROUND(AVG(CAST(re.valor AS FLOAT)), 2) AS cumplimiento_promedio
    FROM ejercicio_rb ej
    JOIN link_paciente_ejercicio_rb lpe 
        ON ej.id_ej = lpe.id_ej
    JOIN resultado_rb re 
        ON re.id_linkpaej = lpe.id_linkpaej
    WHERE 
        CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
    GROUP BY ej.id_ej, ej.nombre
    ORDER BY cumplimiento_promedio ASC;
    """
    df_ejercicios = pd.read_sql(sql_ej, conn).head(3)
    return df_ejercicios


# 2.13. Empleados con baja adherencia (detalle)
def empleados_con_baja_adherencia(conn, fecha_inicio, fecha_fin, umbral_pct=50):
    sql = f"""
    WITH tot AS (
        SELECT 
            pa.id_pa,
            pa.nombre AS nombre_paciente,
            SUM(lpp.minAdhDias) * DATEDIFF(WEEK, '{fecha_inicio}', '{fecha_fin}') AS programadas
        FROM paciente pa
        JOIN link_paciente_patologia_rb lpp 
            ON pa.id_pa = lpp.id_pa
        GROUP BY pa.id_pa, pa.nombre
    ),
    real AS (
        SELECT 
            pa.id_pa,
            COUNT(DISTINCT CONVERT(date, re.date, 103)) AS dias_hizo
        FROM paciente pa
        JOIN link_paciente_ejercicio_rb lpe 
            ON pa.id_pa = lpe.id_pa
        JOIN resultado_rb re 
            ON re.id_linkpaej = lpe.id_linkpaej
        WHERE 
            CONVERT(date, re.date, 103) BETWEEN '{fecha_inicio}' AND '{fecha_fin}'
            AND CAST(re.valor AS FLOAT) > 0
        GROUP BY pa.id_pa
    )
    SELECT 
        t.id_pa,
        t.nombre_paciente,
        ROUND(
            CASE 
                WHEN t.programadas > 0 
                    THEN 
                        CASE 
                            WHEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 > 100 
                                THEN 100 
                            ELSE (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 
                        END
                ELSE 0 END
            , 2) AS adherencia_pct
    FROM tot t
    LEFT JOIN real r 
        ON t.id_pa = r.id_pa
    WHERE 
        ROUND(
            CASE 
                WHEN t.programadas > 0 
                    THEN 
                        CASE 
                            WHEN (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 > 100 
                                THEN 100 
                            ELSE (CAST(ISNULL(r.dias_hizo,0) AS FLOAT) / t.programadas) * 100 
                        END
                ELSE 0 END
            , 2) < {umbral_pct}
    ORDER BY adherencia_pct ASC;
    """
    return pd.read_sql(sql, conn)

# === 3. PROMPT PARA GPT ===
def construir_prompt_empresa_detallado(fecha_inicio, fecha_fin, total_empleados, activos, adherencia_promedio, mejora_rom, top_ejercicios, bajas_adherencia, bajas_rom):
    prompt = f"""
Estructura del Informe Global de Empresa (Evaluación del Programa Preventivo)

**RESUMEN EJECUTIVO**
- Resumen del periodo cubierto: {fecha_inicio} a {fecha_fin}
- Total empleados evaluados: {total_empleados}
- Empleados activos (>=50% adherencia): {activos}
- Adherencia promedio general: {adherencia_promedio}%
- Mejora promedio ROM: {mejora_rom}%

**ESTADÍSTICAS RELEVANTES**
Por favor, incluye literalmente las siguientes tablas en el informe final, sin resumir ni reescribir sus datos. El estilo del informe debe ser profesional, pero debe mostrar estos datos tal como se presentan a continuación:
1. Ejercicios con peor desempeño (Top 3):
| Ejercicio             | Cumplimiento (%) |
|-----------------------|------------------|
"""
    for _, row in top_ejercicios.iterrows():
        prompt += f"| {row['nombre_ejercicio'][:23]:<23} | {row['cumplimiento_promedio']}% |\n"

    prompt += """

2. Empleados con baja adherencia (<50%):
| Empleado              | Adherencia (%) |
|-----------------------|----------------|
"""
    for _, row in bajas_adherencia.iterrows():
        prompt += f"| {row['nombre_paciente'][:23]:<23} | {row['adherencia_pct']}% |\n"

    prompt += """

3. Empleados con mejora ROM <10%:
| Empleado              | Mejora ROM (%) |
|-----------------------|----------------|
"""
    for _, row in bajas_rom.iterrows():
        nombre = row.get("nombre_paciente", f"ID {row['id_pa']}")
        prompt += f"| {nombre[:23]:<23} | {row['rom_pct_cambio']}% |\n"

    prompt += """
**ANÁLISIS DE LOS DATOS**
- Detecta tendencias globales: ¿hubo mejora general? ¿estancamiento? ¿retrocesos?
- Relaciona niveles de adherencia con mejora ROM.
- Identifica si existe correlación entre baja adherencia y peor desempeño en ciertos ejercicios.
- Comenta cualquier hallazgo llamativo (por ejemplo, que la adherencia global es buena pero el ROM progresa poco).

**CONCLUSIONES Y RECOMENDACIONES**
- Resumen general del rendimiento del programa.
- Áreas de mejora prioritarias.
- Recomendaciones prácticas y claras para la empresa (ej. aumentar control de adherencia en empleados con baja mejora, sustituir o reforzar ejercicios con menor cumplimiento).
- Proyección estimada si se mantienen los valores actuales.

Redacta este informe de forma profesional, clara y ejecutiva, siguiendo ese esquema y conclusiones accionables.
"""

    return prompt


# === 4. LLAMADA A GPT ===

def generar_informe_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Eres un experto en fisioterapia laboral redactando informes corporativos."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content


# === 5. GENERACIÓN DE GRÁFICOS ===

# ==================================
# 3. GENERACIÓN DE GRÁFICAS (GUARDAR PNG)
# ==================================

def crear_grafico_adherencia(df_adherencia):
    """
    Gráfica de barras de adherencia semanal (%), con cap en 100%.
    Guarda como 'graf_adherencia.png'.
    """
    if df_adherencia.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(df_adherencia['periodo'].astype(str), df_adherencia['adherencia_periodo_pct'], color='skyblue')
    ax.set_title("Adherencia Semanal Promedio (%)")
    ax.set_xlabel("Semana")
    ax.set_ylabel("Adherencia (%)")
    ax.set_ylim(0, 100)
    plt.tight_layout()
    path = "graf_adherencia.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def crear_grafico_dolor(df_dolor):
    """
    Gráfica de línea de evolución del dolor.
    Guarda como 'graf_dolor.png'.
    """
    if df_dolor.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(df_dolor['periodo'], df_dolor['promedio_puntaje'], marker='o', color='red')
    ax.set_title("Evolución del Dolor Promedio por Semana")
    ax.set_xlabel("Semana")
    ax.set_ylabel("Dolor Promedio")
    plt.tight_layout()
    path = "graf_dolor.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def crear_grafico_ansiedad(df_ansiedad):
    """
    Gráfica de línea de evolución de la ansiedad.
    Guarda como 'graf_ansiedad.png'.
    """
    if df_ansiedad.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(df_ansiedad['periodo'], df_ansiedad['promedio_puntaje'], marker='o', color='orange')
    ax.set_title("Evolución de la Ansiedad Promedio por Semana")
    ax.set_xlabel("Semana")
    ax.set_ylabel("Ansiedad Promedio")
    plt.tight_layout()
    path = "graf_ansiedad.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def crear_grafico_rom(df_rom):
    if df_rom.empty:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot(df_rom['periodo'], df_rom['rom_prom'], marker='s', color='green')
    ax.set_title("Evolución del Coeficiente de Calidad de Movimiento (CQ%)")
    ax.set_xlabel("Semana")
    ax.set_ylabel("CQ Promedio (%)")
    ax.set_ylim(70, 110)
    plt.tight_layout()
    path = "graf_rom.png"
    fig.savefig(path)
    plt.close(fig)
    return path


# === 6. GENERACIÓN DE PDF ===

def limpiar_unicode(texto):
    return (texto.replace(">=", ">=")
                 .replace("≤", "<=")
                 .replace("—", "-")
                 .replace("–", "-")
                 .replace("•", "-")
                 .replace("“", '"')
                 .replace("”", '"')
                 .replace("‘", "'")
                 .replace("’", "'"))


def exportar_pdf_empresa_simple(texto, nombre_archivo, empresa_data, informe_data):
    from fpdf import FPDF

    def agregar_titulo_seccion(pdf, titulo):
        pdf.set_font("Arial", 'B', 13)
        pdf.set_fill_color(0, 70, 140)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 10, titulo, ln=True, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Logo
    try:
        pdf.image("Logo-RehBody-07.png", x=10, y=8, w=30)
    except RuntimeError:
        print("⚠️ No se pudo cargar el logo. Asegúrate de que 'Logo-RehBody-07.png' exista.")
    pdf.ln(25)

    # Título
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Informe Global de Empresa - Programa Preventivo", ln=True, align="C")
    pdf.ln(10)

    # Datos principales
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f'Periodo del informe: {empresa_data["periodo_informe"]}', ln=True)
    pdf.cell(0, 10, f'Fecha de generación: {empresa_data["fecha_informe"]}', ln=True)
    pdf.cell(0, 10, f'Total empleados evaluados: {empresa_data["total_empleados"]}', ln=True)
    pdf.cell(0, 10, f'Empleados activos (>=50% adherencia): {empresa_data["empleados_activos"]}', ln=True)
    pdf.ln(5)

    # Sección Resumen Ejecutivo
    agregar_titulo_seccion(pdf, "RESUMEN Y ANÁLISIS")

    # Informe de texto generado (GPT)
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
    if "graficos" in informe_data and isinstance(informe_data["graficos"], dict) and informe_data["graficos"]:
        pdf.add_page()
        agregar_titulo_seccion(pdf, "GRÁFICAS Y MÉTRICAS DEL PROGRAMA")

        for nombre, ruta in informe_data["graficos"].items():
            if ruta is not None and os.path.exists(ruta):
                try:
                    pdf.set_font("Arial", 'B', 11)
                    pdf.cell(0, 8, nombre, ln=True, align="C")
                    pdf.image(ruta, w=180)
                    pdf.ln(5)
                    print(f"✅ Gráfico '{nombre}' insertado correctamente")
                except RuntimeError as e:
                    print(f"⚠️ Error al insertar gráfico {nombre}: {e}")
            else:
                print(f"⚠️ Ruta no encontrada o vacía para gráfico '{nombre}'")

    # Guardar PDF
    pdf.output(nombre_archivo)
    print(f"📄 Informe guardado como {nombre_archivo}")




# === 7. EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    fecha_inicio = input("📅 Fecha inicio (YYYY-MM-DD): ").strip()
    fecha_fin = input("📅 Fecha fin (YYYY-MM-DD): ").strip()

    try:
        datetime.strptime(fecha_inicio, "%Y-%m-%d")
        datetime.strptime(fecha_fin, "%Y-%m-%d")
    except ValueError:
        print("❌ Formato de fecha inválido. Usa YYYY-MM-DD.")
        exit(1)

    conn = conectar_bd()
    if not conn:
        exit(1)

    # Datos resumen
    df_total = numero_total_empleados(conn, fecha_inicio, fecha_fin)
    df_activos = numero_empleados_activos(conn, fecha_inicio, fecha_fin)
    df_adh = adherencia_general(conn, fecha_inicio, fecha_fin)
    df_rom = mejora_promedio_rom(conn, fecha_inicio, fecha_fin)

    total = df_total.iloc[0, 0]
    activos = df_activos.iloc[0, 0]
    adherencia_promedio = df_adh.iloc[0, 0]
    mejora_rom = df_rom.iloc[0, 0]

    # Consultar áreas críticas y alertas
    df_criticos = areas_criticas_necesitan_atencion(conn, fecha_inicio, fecha_fin)
    df_baja_adherencia = empleados_con_baja_adherencia(conn, fecha_inicio, fecha_fin)
    _, df_baja_rom = alertas_bajo_desempeno(conn, fecha_inicio, fecha_fin)

    # Prompt y respuesta GPT
    prompt = construir_prompt_empresa_detallado(
        fecha_inicio, fecha_fin,
        total, activos, adherencia_promedio, mejora_rom,
        df_criticos, df_baja_adherencia, df_baja_rom
    )
    informe = generar_informe_gpt(prompt)

    # Gráficos
    df_adherencia_sem = evolucion_adherencia_tiempo(conn, fecha_inicio, fecha_fin)
    df_dolor = evolucion_estado_salud_global(conn, fecha_inicio, fecha_fin, 9)
    df_ansiedad = evolucion_estado_salud_global(conn, fecha_inicio, fecha_fin, 29)
    df_rom = evolucion_rom_global(conn, fecha_inicio, fecha_fin)

    path_grafico_adherencia = crear_grafico_adherencia(df_adherencia_sem)
    path_grafico_dolor = crear_grafico_dolor(df_dolor)
    path_grafico_ansiedad = crear_grafico_ansiedad(df_ansiedad)
    path_grafico_rom = crear_grafico_rom(df_rom)

    # Datos para PDF
    empresa_data = {
        "periodo_informe": f"{fecha_inicio} a {fecha_fin}",
        "fecha_informe": datetime.today().strftime("%Y-%m-%d"),
        "total_empleados": total,
        "empleados_activos": activos
    }

    informe_data = {
        "graficos": {
            "Adherencia semanal": path_grafico_adherencia,
             "Evolución Dolor": path_grafico_dolor,
            "Evolución Ansiedad": path_grafico_ansiedad,
            "Evolución ROM": path_grafico_rom
        }
    }

    # Exportar PDF con logo y formato simple
    exportar_pdf_empresa_simple(
        informe,
        f"informe_empresa_{fecha_inicio}_a_{fecha_fin}.pdf",
        empresa_data,
        informe_data
    )

    conn.close()
    print("✅ Informe de empresa generado correctamente.")


