/**
 * Esquema de validación para los 7 archivos crudos del HIS del Hospital Susana López de Valencia.
 * Extraído directamente de etl/build_db.py y verificado con los archivos crudos en DATOS/*.txt.
 */

export const EXPECTED_COLUMNS = {
  atencion: [
    "OidIngreso",
    "FechaAtencion"
  ],
  paciente: [
    "TipoDocumento",
    "IdPaciente",
    "NombrePaciente",
    "FechaNacimiento",
    "Sexo",
    "Asegurador",
    "Regimen",
    "Departamento",
    "Municipio",
    "Zona"
  ],
  ingresos: [
    "OidIngreso",
    "ConsecutivoIngreso",
    "IdPaciente",
    "ClaseIngreso",
    "ViaIngreso",
    "TipoRiesgo",
    "FechaIngreso",
    "FechaHospitalizacion",
    "OidTriageA",
    "CodigoCama",
    "NombreCama",
    "NombreGrupoCama",
    "NombreSubgrupoCama",
    "CodigoDiagnostico",
    "NombreDiagnostico"
  ],
  programacion_cirugia: [
    "ConsecutivoProgramacion",
    "IdPaciente",
    "OidIngreso",
    "CodigoServicio"
  ],
  triage: [
    "OidTriage",
    "FechaTriage",
    "MotivoConsulta",
    "TensionArterial",
    "FrecuenciaCardiaca",
    "FrecuenciaRespiratoria",
    "Temperatura",
    "IdPaciente2",
    "CodigoTriage",
    "ClasificacionTriage"
  ],
  medicamentos_insumos: [
    "OidIngreso",
    "CodigoServicio",
    "NombreServicio",
    "Cantidad",
    "FechaPrestacion",
    "AreaServicio",
    "Especialidad",
    "OidMI"
  ],
  servicios: [
    "OidIngreso",
    "CodigoServicio",
    "NombreServicio",
    "Cantidad",
    "FechaPrestacion",
    "CodigoAreaServicio",
    "AreaServicio",
    "Especialidad",
    "OidS"
  ]
};

export const FILE_METADATA = {
  atencion: {
    label: "Atención (primera consulta)",
    filename: "Atencion.txt",
    separator: "|",
    encoding: "utf-8"
  },
  paciente: {
    label: "Paciente (demografía y afiliación)",
    filename: "Paciente.txt",
    separator: "|",
    encoding: "utf-8"
  },
  ingresos: {
    label: "Ingresos (episodios y camas)",
    filename: "Ingresos.txt",
    separator: "|",
    encoding: "utf-8"
  },
  programacion_cirugia: {
    label: "Programación de Cirugía (quirófanos)",
    filename: "ProgramacionCirugia.txt",
    separator: "|",
    encoding: "utf-8"
  },
  triage: {
    label: "Triage (signos vitales y clasificación)",
    filename: "Triage.txt",
    separator: "|",
    encoding: "utf-8"
  },
  medicamentos_insumos: {
    label: "Medicamentos e Insumos (dispensación)",
    filename: "MedicamentoInsumo.txt",
    separator: "|",
    encoding: "utf-8"
  },
  servicios: {
    label: "Servicios (procedimientos y estancia)",
    filename: "Servicios.txt",
    separator: "|",
    encoding: "utf-8"
  }
};
