import streamlit as st
from datetime import datetime
from generador_informes import generar_informe_paciente
from resumen_empresa_mejorado import (
    conectar_bd,
    numero_total_empleados,
    numero_empleados_activos,
    adherencia_general,
    porcentaje_empleados_activos,
    porcentaje_finalizacion_ejercicios,
    evaluacion_global_estado_salud,
    mejora_promedio_rom,
    evolucion_adherencia_tiempo,
    evolucion_estado_salud_global,
    evolucion_rom_global,
    alertas_bajo_desempeno,
    areas_criticas_necesitan_atencion,
    empleados_con_baja_adherencia,
    crear_grafico_adherencia,
    crear_grafico_dolor,
    crear_grafico_ansiedad,
    crear_grafico_rom,
    construir_prompt_empresa_detallado,
    generar_informe_gpt,
    exportar_pdf_empresa_simple
)

st.set_page_config(page_title="TFG: Generador de Informes", page_icon="📊")

st.title("📊 Generador de Informes del Programa Preventivo")

modo = st.radio("Selecciona el tipo de informe", ["Informe individual por paciente", "Resumen global por empresa"])

# ================================================
# 🔹 MODO INDIVIDUAL
# ================================================
if modo == "Informe individual por paciente":
    st.header("🧍 Informe de Paciente")

    with st.form("form_individual"):
        id_pa = st.text_input("ID del paciente")
        fecha_inicio = st.date_input("Fecha de inicio")
        fecha_fin = st.date_input("Fecha de fin")
        submit_ind = st.form_submit_button("Generar informe individual")

    if submit_ind:
        if not id_pa.isdigit():
            st.error("❌ El ID debe ser un número entero.")
        elif fecha_inicio > fecha_fin:
            st.error("❌ La fecha de inicio no puede ser posterior a la de fin.")
        else:
            try:
                generar_informe_paciente(
                    int(id_pa),
                    fecha_inicio.strftime("%Y-%m-%d"),
                    fecha_fin.strftime("%Y-%m-%d")
                )
                st.success("✅ Informe generado con éxito.")
            except Exception as e:
                st.error(f"❌ Error al generar el informe: {e}")

# ================================================
# 🔹 MODO EMPRESA
# ================================================
else:
    st.header("🏢 Resumen Global de la Empresa")

    with st.form("form_empresa"):
        fecha_inicio = st.date_input("Fecha de inicio (empresa)", key="fi_empresa")
        fecha_fin = st.date_input("Fecha de fin (empresa)", key="ff_empresa")
        submit_emp = st.form_submit_button("Generar informe colectivo")

    if submit_emp:
        if fecha_inicio > fecha_fin:
            st.error("❌ La fecha de inicio no puede ser posterior a la de fin.")
        else:
            try:
                conn = conectar_bd()
                if conn is None:
                    st.error("❌ No se pudo conectar a la base de datos.")
                else:
                    fi_str = fecha_inicio.strftime("%Y-%m-%d")
                    ff_str = fecha_fin.strftime("%Y-%m-%d")

                    df_total = numero_total_empleados(conn, fi_str, ff_str)
                    df_activos = numero_empleados_activos(conn, fi_str, ff_str)
                    df_adherencia_gen = adherencia_general(conn, fi_str, ff_str)
                    df_pct_activos = porcentaje_empleados_activos(conn, fi_str, ff_str)
                    df_pct_finalizar = porcentaje_finalizacion_ejercicios(conn, fi_str, ff_str)
                    df_eval_salud = evaluacion_global_estado_salud(conn, fi_str, ff_str)
                    df_mejora_rom = mejora_promedio_rom(conn, fi_str, ff_str)

                    df_evol_adherencia = evolucion_adherencia_tiempo(conn, fi_str, ff_str)
                    df_evol_dolor = evolucion_estado_salud_global(conn, fi_str, ff_str, id_escala=9)
                    df_evol_ansiedad = evolucion_estado_salud_global(conn, fi_str, ff_str, id_escala=29)
                    df_evol_rom = evolucion_rom_global(conn, fi_str, ff_str)

                    df_ad_baja, df_rom_baja = alertas_bajo_desempeno(conn, fi_str, ff_str)
                    df_crit_ej = areas_criticas_necesitan_atencion(conn, fi_str, ff_str)
                    df_baja_ad = empleados_con_baja_adherencia(conn, fi_str, ff_str)

                    rutas = {
                        "Adherencia semanal": crear_grafico_adherencia(df_evol_adherencia),
                        "Evolución Dolor": crear_grafico_dolor(df_evol_dolor),
                        "Evolución Ansiedad": crear_grafico_ansiedad(df_evol_ansiedad),
                        "Evolución ROM": crear_grafico_rom(df_evol_rom)
                    }

                    prompt = construir_prompt_empresa_detallado(
                        fi_str, ff_str,
                        int(df_total.iloc[0,0]),
                        int(df_activos.iloc[0,0]),
                        float(df_adherencia_gen.iloc[0,0]),
                        float(df_mejora_rom.iloc[0,0]),
                        df_crit_ej,
                        df_baja_ad,
                        df_rom_baja
                    )

                    texto_resumen = generar_informe_gpt(prompt)

                    empresa_data = {
                        "periodo_informe": f"{fi_str} a {ff_str}",
                        "fecha_informe": datetime.today().strftime("%Y-%m-%d"),
                        "total_empleados": int(df_total.iloc[0, 0]),
                        "empleados_activos": int(df_activos.iloc[0, 0])
                    }

                    informe_data = {"graficos": rutas}

                    exportar_pdf_empresa_simple(
                        texto_resumen,
                        f"informe_empresa_{fi_str}_a_{ff_str}.pdf",
                        empresa_data,
                        informe_data
                    )

                    st.success("✅ Informe colectivo generado con éxito.")
                    st.info("📄 El archivo PDF se ha guardado en el directorio actual.")
                    conn.close()

            except Exception as e:
                st.error(f"❌ Error al generar el informe colectivo: {e}")
