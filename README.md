# Sistema de Generación de Informes Clínicos Automáticos y Asistente Predictivo para PRL (RehBody)

Este repositorio contiene el código fuente y el modelo de datos desarrollados para el Trabajo Fin de Grado en **Ingeniería de la Salud** (Universidad de Sevilla) por **Diego Sosa Arteaga**, titulado:
> *"Desarrollo de un asistente predictivo para el seguimiento personalizado de trabajadores en programas de prevención de riesgos laborales"*.

## Descripción del Proyecto

El proyecto aborda la necesidad de realizar un seguimiento automático, cuantitativo y personalizado a los trabajadores participantes en programas preventivos de trastornos musculoesqueléticos (TME) dentro de la plataforma de telerrehabilitación **RehBody** (*Healthinn*).

A partir de los datos registrados durante el entrenamiento mediante algoritmos de visión por computador (Rango de Movimiento - ROM, calidad del gesto) y cuestionarios validados (escalas de dolor END y ansiedad NRS-A), el sistema procesa, analiza y automatiza la redacción de informes evolutivos clínicos (individuales) y ejecutivos (colectivos para empresas).

## Tecnologías y Arquitectura

* **Lenguaje principal:** Python 3.x
* **Base de datos:** Microsoft SQL Server (`pyodbc`, modelo relacional entidad-relación)
* **IA Generativa y NLP:** OpenAI API (GPT-4) mediante *prompt engineering* estructurado para extracción y traducción de datos numéricos a texto clínico profesional en castellano.
* **Procesamiento de datos y gráficos:** `pandas`, `numpy`, `matplotlib`
* **Interfaz de usuario:** Streamlit (Panel de control web ligero e interactivo)
* **Generación de documentos:** `fpdf` (Maquetación dinámica de informes en formato PDF)
* **Testing y Calidad:** Katalon Recorder (Pruebas de interfaz automatizadas)

## Estructura del Repositorio

* `app_generador.py`: Punto de entrada de la aplicación web en Streamlit. Gestiona la interfaz gráfica, recepción de parámetros (IDs, fechas) y control de errores/validaciones de entrada.
* `generador_informes.py`: Módulo encargado de la lógica individual por paciente. Realiza las consultas SQL, calcula la adherencia semanal, evolutivos de dolor/ROM y la métrica CQ (*Coeficiente de Calidad del Movimiento*), genera los gráficos, construye el prompt dinámico y llama a la API de OpenAI para producir el PDF final.
* `resumen_empresa_mejorado.py`: Módulo enfocado en la visión corporativa agregada. Procesa métricas globales, identifica alertas clínicas (baja adherencia, estancamiento en ROM), genera gráficos colectivos y redacta un informe ejecutivo consolidado.
* `BaseDatosTFG.sql`: Script SQL con la definición de tablas, relaciones y consultas para el modelo relacional.
* `Logo-RehBody-07.png`: Recurso gráfico integrado dinámicamente en la cabecera de los informes PDF.

## Funcionalidades Principales

1. **Informes Individuales para Especialistas:** Evaluación detallada de adherencia, evolución semanal del dolor y variación del Coeficiente de Calidad del Movimiento (CQ), junto con una narrativa médica personalizada.
2. **Informes Colectivos para Empresas:** Análisis agregados de salud laboral, porcentaje de empleados activos (umbral >50% adherencia) y sistema de alertas tempranas sobre áreas críticas y ejercicios con menor rendimiento.
3. **Generación PDF e Integración:** Exportación automática de informes maquetados con gráficos y texto interpretativo listos para adjuntar a historias clínicas o presentaciones directivas.
