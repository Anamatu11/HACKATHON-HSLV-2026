"""
Glosario de términos del sector salud (fuente: DATOS/Glosario_Terminos_Salud_HIS.pdf, 22-sep-2026).

Responsable: Rol A.

Base de conocimiento del agente para preguntas conceptuales ("¿qué es una EPS?"). Son ~35 términos:
caben completos en el prompt del LLM, así que no hace falta un RAG con embeddings. Sin LLM, el agente
responde directamente con estas definiciones (la demo no depende de la red).

`definition` es el texto del glosario oficial. `data_note` (opcional) explica cómo aparece el término en
hospital.db; es aporte del equipo, no del glosario, y se presenta como tal.
"""
import re
import unicodedata

SOURCE_NAME = "Glosario de Términos del Sector Salud HIS"

GLOSSARY: list[dict] = [
    # --- Siglas y sistemas del sector salud ---
    {"term": "HIS", "category": "Siglas y sistemas", "aliases": ["sistema de informacion hospitalaria"],
     "definition": "Sistema de Información Hospitalaria (Hospital Information System): el software que administra "
                   "los procesos clínicos y administrativos de una institución de salud: admisiones, historia clínica, "
                   "servicios, facturación, etc.",
     "data_note": "Los datos de este panel son un extracto del HIS del hospital."},
    {"term": "IPS", "category": "Siglas y sistemas", "aliases": ["institucion prestadora"],
     "definition": "Institución Prestadora de Servicios de Salud: la entidad (clínica, hospital, centro médico) que "
                   "presta directamente los servicios de salud al paciente.",
     "data_note": "El Hospital Susana López de Valencia es una IPS."},
    {"term": "EPS", "category": "Siglas y sistemas", "aliases": ["entidad promotora"],
     "definition": "Entidad Promotora de Salud: aseguradora que administra la afiliación de las personas al sistema "
                   "de salud colombiano y gestiona su acceso a los servicios.",
     "data_note": "es el asegurador que aparece en el registro de cada paciente."},
    {"term": "ARL", "category": "Siglas y sistemas", "aliases": ["riesgos laborales"],
     "definition": "Administradora de Riesgos Laborales: aseguradora que cubre los accidentes de trabajo y las "
                   "enfermedades de origen laboral."},
    {"term": "RIPS", "category": "Siglas y sistemas", "aliases": ["registro individual de prestacion"],
     "definition": "Registro Individual de Prestación de Servicios de Salud: el reporte oficial que las IPS deben "
                   "enviar al sistema de salud colombiano con el detalle de cada servicio prestado."},
    {"term": "CUPS", "category": "Siglas y sistemas", "aliases": ["clasificacion unica de procedimientos"],
     "definition": "Clasificación Única de Procedimientos en Salud: catálogo oficial colombiano de códigos para "
                   "procedimientos y servicios médicos.",
     "data_note": "es el código con el que se registra cada servicio o procedimiento prestado."},
    {"term": "CIE-10", "category": "Siglas y sistemas", "aliases": ["cie 10", "cie10", "clasificacion internacional de enfermedades"],
     "definition": "Clasificación Internacional de Enfermedades, décima versión: catálogo internacional de códigos "
                   "de diagnóstico.",
     "data_note": "En el panel los diagnósticos se agrupan por capítulo (la letra inicial del código: J = respiratorio, "
                  "O = embarazo, S/T = traumatismos) para no exponer diagnósticos individuales."},

    # --- Documentos de identificación ---
    {"term": "CC", "category": "Documentos de identificación", "aliases": ["cedula de ciudadania"],
     "definition": "Cédula de Ciudadanía: documento de identidad estándar para adultos colombianos."},
    {"term": "TI", "category": "Documentos de identificación", "aliases": ["tarjeta de identidad"],
     "definition": "Tarjeta de Identidad: documento de identidad para menores de edad (entre 7 y 17 años) en Colombia."},
    {"term": "CE", "category": "Documentos de identificación", "aliases": ["cedula de extranjeria"],
     "definition": "Cédula de Extranjería: documento de identidad para extranjeros residentes en Colombia."},
    {"term": "RC", "category": "Documentos de identificación", "aliases": ["registro civil"],
     "definition": "Registro Civil de Nacimiento: documento de identidad para niños menores de 7 años."},
    {"term": "PA", "category": "Documentos de identificación", "aliases": ["pasaporte"],
     "definition": "Pasaporte."},
    {"term": "CN", "category": "Documentos de identificación", "aliases": ["certificado de nacido vivo"],
     "definition": "Certificado de Nacido Vivo: documento que identifica a un recién nacido antes de que tenga "
                   "registro civil."},
    {"term": "PPT", "category": "Documentos de identificación", "aliases": ["permiso por proteccion temporal"],
     "definition": "Permiso por Protección Temporal: documento que permite a ciudadanos extranjeros (principalmente "
                   "venezolanos) acceder a servicios en Colombia."},
    {"term": "ASI", "category": "Documentos de identificación", "aliases": ["adulto sin identificar"],
     "definition": "Adulto Sin Identificar: persona adulta atendida sin ningún documento de identidad disponible."},
    {"term": "MSI", "category": "Documentos de identificación", "aliases": ["menor sin identificar"],
     "definition": "Menor Sin Identificar: persona menor de edad atendida sin ningún documento de identidad disponible."},
    {"term": "DIE", "category": "Documentos de identificación", "aliases": ["documento de identificacion extranjero"],
     "definition": "Documento de Identificación Extranjero: variante local del documento de identidad extranjero, "
                   "equivalente a la Cédula de Extranjería."},
    {"term": "SA", "category": "Documentos de identificación", "aliases": ["salvoconducto"],
     "definition": "Salvoconducto (de permanencia): documento temporal de identificación para personas en trámite "
                   "de regularización migratoria."},

    # --- Afiliación y aseguramiento ---
    {"term": "Régimen (de afiliación)", "category": "Afiliación y aseguramiento",
     "aliases": ["regimen", "contributivo", "subsidiado", "vinculado", "regimen particular"],
     "definition": "La categoría bajo la cual una persona está vinculada al sistema de salud colombiano. "
                   "Contributivo: afiliados que cotizan (trabajadores o independientes). Subsidiado: población de bajos "
                   "ingresos, afiliada sin cotizar, subsidiada por el Estado. Vinculado: personas sin afiliación formal, "
                   "atendidas mientras se les asigna un régimen. Particular: personas que pagan directamente el "
                   "servicio, sin pasar por una aseguradora. Otro: cualquier categoría no clasificada en las anteriores."},
    {"term": "Asegurador", "category": "Afiliación y aseguramiento", "aliases": ["aseguradora"],
     "definition": "La EPS, ARL u otra entidad responsable de pagar o autorizar la atención del paciente."},

    # --- Proceso de atención ---
    {"term": "Ingreso / Admisión", "category": "Proceso de atención", "aliases": ["ingreso", "admision", "episodio de atencion"],
     "definition": "El registro de un episodio de atención de un paciente en la institución, desde que llega hasta "
                   "que es dado de alta. No equivale a una visita al médico sino a todo el episodio.",
     "data_note": "es la unidad central de análisis; un mismo paciente puede tener varios ingresos (el 17% tiene más de uno)."},
    {"term": "Clase de ingreso", "category": "Proceso de atención", "aliases": ["ambulatorio", "hospitalario"],
     "definition": "Indica si la atención fue Ambulatoria (sin hospitalización) u Hospitalaria (con internación).",
     "data_note": "En estos datos, 'Ambulatorio' corresponde principalmente a urgencias atendidas sin hospitalizar."},
    {"term": "Vía de ingreso", "category": "Proceso de atención", "aliases": ["via de ingreso", "remitido"],
     "definition": "El punto de entrada del paciente a la institución: Urgencias, Hospitalización (programada), "
                   "Remitido (referido desde otra institución) o Cirugía Ambulatoria."},
    {"term": "Tipo de riesgo", "category": "Proceso de atención", "aliases": ["tipo de riesgo"],
     "definition": "El origen del evento que causó la atención, usado para fines legales y de facturación: accidente de "
                   "trabajo, accidente de tránsito, accidente en el hogar, enfermedad general, enfermedad profesional, "
                   "atención inicial de urgencias, atención de población perinatal (madre o recién nacido), evento "
                   "catastrófico de origen natural, lesión autoinfligida, lesión por agresión u otro tipo de accidente."},
    {"term": "Triage", "category": "Proceso de atención", "aliases": ["triaje", "clasificacion de triage"],
     "definition": "Proceso de clasificación de pacientes en urgencias según la gravedad de su condición clínica, para "
                   "decidir quién se atiende primero (no por orden de llegada). En Colombia suele usarse una escala de "
                   "5 niveles, donde Triage I es el más urgente y Triage V el menos urgente.",
     "data_note": "En los datos del hospital se registran los niveles 1 a 4, en áreas de Adultos, Pediatría y "
                  "Ginecología. La espera se mide desde el triage hasta la primera atención médica."},
    {"term": "Motivo de consulta", "category": "Proceso de atención", "aliases": ["motivo de consulta"],
     "definition": "La razón, en palabras del paciente o del profesional que lo atiende, por la que se solicita la atención.",
     "data_note": "Por privacidad no se carga en la base del panel: es texto libre que puede contener datos personales."},
    {"term": "Diagnóstico (principal)", "category": "Proceso de atención", "aliases": ["diagnostico"],
     "definition": "La condición de salud identificada por el profesional tratante, codificada con CIE-10.",
     "data_note": "El agente solo lo entrega agregado por capítulo CIE-10, nunca por paciente."},
    {"term": "Especialidad (médica)", "category": "Proceso de atención", "aliases": ["especialidad"],
     "definition": "La rama de la medicina del profesional que prestó el servicio, por ejemplo Medicina General, "
                   "Cirugía o Pediatría."},
    {"term": "Área de servicio", "category": "Proceso de atención", "aliases": ["area de servicio"],
     "definition": "La unidad funcional de la institución donde se prestó el servicio, por ejemplo Laboratorio Clínico, "
                   "Farmacia u Hospitalización."},
    {"term": "Programación quirúrgica", "category": "Proceso de atención",
     "aliases": ["programacion quirurgica", "programacion de cirugia", "cirugia programada"],
     "definition": "El proceso de agendar una cirugía o procedimiento quirúrgico antes de realizarlo. Puede no coincidir "
                   "con la ejecución real: una cirugía programada puede no ejecutarse, y una ejecutada puede no haber "
                   "sido programada previamente.",
     "data_note": "El panel considera 'realizada' una cirugía cuyo procedimiento aparece facturado en el ingreso."},

    # --- Signos vitales ---
    {"term": "Tensión arterial", "category": "Signos vitales", "aliases": ["tension arterial", "presion arterial"],
     "definition": "Presión de la sangre sobre las arterias, expresada como dos números (sistólica/diastólica), "
                   "por ejemplo 120/80."},
    {"term": "Frecuencia cardiaca", "category": "Signos vitales", "aliases": ["frecuencia cardiaca", "pulso"],
     "definition": "Número de latidos del corazón por minuto."},
    {"term": "Frecuencia respiratoria", "category": "Signos vitales", "aliases": ["frecuencia respiratoria"],
     "definition": "Número de respiraciones por minuto."},
    {"term": "Temperatura", "category": "Signos vitales", "aliases": ["temperatura corporal"],
     "definition": "Temperatura corporal del paciente, en grados Celsius."},

    # --- Términos técnicos del modelo de datos ---
    {"term": "OID", "category": "Términos del modelo de datos", "aliases": ["oidingreso", "oidtriage"],
     "definition": "En este archivo NO es el identificador estándar ISO/ASN.1. Es solo el prefijo que el HIS usa para "
                   "nombrar sus identificadores numéricos internos; equivale a un ID autoincremental de base de datos."},
    {"term": "Consecutivo", "category": "Términos del modelo de datos", "aliases": ["consecutivo"],
     "definition": "Número secuencial asignado internamente a un registro, de uso administrativo (similar a un "
                   "identificador, pero pensado para control interno más que para relacionar tablas)."},
]

# Indicadores del panel: definiciones del EQUIPO (no del glosario oficial). Se citan con su propia fuente.
PANEL_SOURCE_NAME = "Definiciones de indicadores del panel HSLV"
PANEL_TERMS: list[dict] = [
    {"term": "Ocupación física", "category": "Indicadores del panel",
     "aliases": ["ocupacion fisica", "ocupacion de camas", "ocupacion hospitalaria", "porcentaje de ocupacion"],
     "definition": "Pacientes presentes a las 12:00 del día dividido por las camas físicas del servicio (sin contar "
                   "camas virtuales). Si pasa de 100%, hay pacientes ubicados en camas virtuales de expansión.",
     "data_note": "la capacidad de camas es estimada a partir de las camas distintas usadas en el periodo."},
    {"term": "Cama virtual", "category": "Indicadores del panel", "aliases": ["camas virtuales", "sobreocupacion"],
     "definition": "Cama registrada en el sistema para ubicar pacientes cuando las camas físicas se agotan. "
                   "Su uso indica sobreocupación del servicio."},
    {"term": "Tiempo de espera en urgencias", "category": "Indicadores del panel",
     "aliases": ["tiempo de espera", "espera en urgencias"],
     "definition": "Minutos entre la clasificación de triage y la primera atención médica del paciente.",
     "data_note": "la meta usada para triage 2 es de máximo 30 minutos."},
    {"term": "Días de inventario", "category": "Indicadores del panel",
     "aliases": ["dias de inventario", "stock critico", "desabastecimiento"],
     "definition": "Unidades en stock divididas por el consumo diario promedio de los últimos 30 días: cuántos días "
                   "alcanza el medicamento si el consumo sigue igual. Menos de 5 días es alerta; menos de 2, crítico.",
     "data_note": "el consumo es real, pero el stock y los vencimientos son simulados porque los datos no los incluyen."},
    {"term": "Cirugía realizada", "category": "Indicadores del panel",
     "aliases": ["cirugia realizada", "cirugias realizadas", "cumplimiento quirurgico"],
     "definition": "Cirugía programada cuyo procedimiento aparece facturado en el ingreso del paciente. "
                   "El cumplimiento es realizadas sobre programadas.",
     "data_note": "solo el 31% de las programaciones se puede cruzar con un ingreso; las demás no se evalúan."},
    {"term": "Alerta predictiva", "category": "Indicadores del panel",
     "aliases": ["alertas predictivas", "prediccion", "tendencia"],
     "definition": "Aviso de que un grupo de diagnósticos (capítulo CIE-10) crece al menos 15% en ingresos diarios en "
                   "las últimas 2 semanas frente a las 4 anteriores. Recomienda los medicamentos más característicos "
                   "de ese grupo para anticipar su stock."},
]
for _entry in GLOSSARY:
    _entry.setdefault("source", SOURCE_NAME)
for _entry in PANEL_TERMS:
    _entry["source"] = PANEL_SOURCE_NAME
ALL_TERMS = GLOSSARY + PANEL_TERMS

# Preguntas de definición: se detectan al INICIO de la pregunta para no confundir
# "¿Qué servicio tiene más ingresos?" (datos) con "¿Qué es un ingreso?" (concepto).
DEFINITION_PATTERN = re.compile(
    r"^(que (es|son|significa|significan|quiere decir)|define|definicion de|significado de|"
    r"explica(me)?|a que se refiere|para que sirve|cual es la diferencia|que diferencia hay|"
    r"en que se diferencia|como se clasifica|que tipos de)\b")
SHORT_ACRONYM_LEN = 2   # CC, TI, PA...: solo cuentan si vienen en MAYÚSCULAS


def _normalize(text: str) -> str:
    no_accents = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", no_accents.lower()).split())


def is_definition_question(question: str) -> bool:
    return bool(DEFINITION_PATTERN.search(_normalize(question)))


def find_terms(question: str) -> list[dict]:
    """Términos del glosario mencionados en la pregunta, en orden de aparición en el glosario."""
    text = _normalize(question)
    found = []
    for entry in ALL_TERMS:
        term = entry["term"]
        if len(term) <= SHORT_ACRONYM_LEN:
            # Siglas cortas: solo como palabra en mayúsculas ("TI" sí, "para ti" no)
            hit = re.search(rf"(?<![A-Za-zÁÉÍÓÚÑáéíóúñ]){re.escape(term)}(?![A-Za-zÁÉÍÓÚÑáéíóúñ])", question)
        else:
            candidates = [_normalize(term)] + [_normalize(a) for a in entry.get("aliases", [])]
            hit = any(re.search(rf"\b{re.escape(c)}\b", text) for c in candidates if c)
        if hit:
            found.append(entry)
    return found


def format_entry(entry: dict) -> str:
    """Texto de una definición para la respuesta sin LLM."""
    text = f"{entry['term']} — {entry['definition']}"
    if note := entry.get("data_note"):
        text += f" Nota del panel: {note[0].upper()}{note[1:]}"
    return text


def sources_of(entries: list[dict]) -> list[str]:
    """Fuentes citadas, sin repetir y en orden."""
    return list(dict.fromkeys(e["source"] for e in entries))


def glossary_prompt_text() -> str:
    """Glosario oficial + indicadores del panel, para el prompt del sistema del LLM."""
    def block(title: str, entries: list[dict]) -> str:
        return f"{title}:\n" + "\n".join(
            f"- {e['term']} ({e['category']}): {e['definition']}"
            + (f" [En estos datos: {e['data_note']}]" if e.get("data_note") else "") for e in entries)
    return f"{block(f'Glosario ({SOURCE_NAME})', GLOSSARY)}\n\n{block(PANEL_SOURCE_NAME, PANEL_TERMS)}"
