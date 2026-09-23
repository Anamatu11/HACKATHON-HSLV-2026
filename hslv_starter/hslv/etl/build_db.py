"""
ETL - Hackathon HSLV 2026
Lee los 7 .txt crudos del HIS, los limpia y genera data/hospital.db (SQLite).

Uso:
    python etl/build_db.py --raw "ruta/a/Insumos Hackaton/Datos" --out data/hospital.db

Se ejecuta UNA vez (o cada vez que cambien los datos crudos). El agente y el
dashboard SOLO leen hospital.db; nunca los .txt.
"""
import argparse
import csv
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42


def read_raw(raw_dir: Path, name: str, **kw) -> pd.DataFrame:
    # QUOTE_NONE: MotivoConsulta trae comillas sueltas que rompen el parser por defecto
    return pd.read_csv(raw_dir / f"{name}.txt", sep="|", dtype=str, encoding="utf-8",
                       quoting=csv.QUOTE_NONE, **kw)


def to_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def fmt_dt(s: pd.Series) -> pd.Series:
    # SQLite no tiene tipo fecha: se guarda texto ISO 'YYYY-MM-DD HH:MM:SS' (ordenable y usable con date()/julianday())
    return s.dt.strftime("%Y-%m-%d %H:%M:%S")


def clean_text(s: pd.Series) -> pd.Series:
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


# ---------------------------------------------------------------- pacientes
def build_patients(raw):
    p = read_raw(raw, "Paciente")
    out = pd.DataFrame({
        "patient_id": p.IdPaciente.astype(int),
        "document_type": p.TipoDocumento,
        "sex": p.Sexo,
        "birth_date": to_dt(p.FechaNacimiento).dt.strftime("%Y-%m-%d"),
        "insurer": clean_text(p.Asegurador),
        "regime": p.Regimen,
        "department": p.Departamento,
        "municipality": p.Municipio,
        "zone": p.Zona,
    })  # NombrePaciente se descarta (dato personal)
    return out


# ---------------------------------------------------------------- triage
def triage_area(label: str) -> str:
    l = label.upper()
    if "GINECO" in l:
        return "Ginecología"
    if "PEDIATR" in l or "UMI" in l:
        return "Pediatría"
    return "Adultos"


def build_triage(raw):
    t = read_raw(raw, "Triage").dropna(subset=["OidTriage"])  # 1.675 filas totalmente vacías
    label = clean_text(t.ClasificacionTriage)
    bp = t.TensionArterial.str.extract(r"(\d{2,3})\s*/\s*(\d{2,3})")
    num = lambda c: pd.to_numeric(t[c].str.replace(",", "."), errors="coerce")
    temp = num("Temperatura")
    temp = temp.where(temp.between(30, 45))  # hay 0.36, 3636, etc.
    hr = num("FrecuenciaCardiaca").where(lambda v: v.between(20, 250))
    rr = num("FrecuenciaRespiratoria").where(lambda v: v.between(5, 100))
    out = pd.DataFrame({
        "triage_id": t.OidTriage.astype(int),
        "patient_id": pd.to_numeric(t.IdPaciente2, errors="coerce").astype("Int64"),
        "triage_at": fmt_dt(to_dt(t.FechaTriage)),
        "triage_code": t.CodigoTriage,
        "triage_label": label,
        "triage_level": label.str.extract(r"TRIAGE\s*(\d)")[0].astype("Int64"),
        "triage_area": label.fillna("").map(triage_area),
        "systolic_bp": pd.to_numeric(bp[0], errors="coerce").where(lambda v: v.between(40, 260)),
        "diastolic_bp": pd.to_numeric(bp[1], errors="coerce").where(lambda v: v.between(20, 180)),
        "heart_rate": hr,
        "respiratory_rate": rr,
        "temperature_c": temp,
    })  # MotivoConsulta se descarta: texto libre, puede contener datos personales
    return out


# ---------------------------------------------------------------- ingresos
RISK_MAP = {
    "Accidente de transito": "Accidente de Tránsito",
    "Accidente de Transito Comun": "Accidente de Tránsito",
    "Accidente en el hogar": "Accidente en el Hogar",
    "Lesion auto inflingida": "Lesión Autoinfligida",
    "Lesion por Agresion": "Lesión por Agresión",
    "Atencion Poblacion Perinatal": "Atención Población Perinatal",
    "Atencion Inicial Urgencias": "Atención Inicial Urgencias",
    "Evento catastrofico de Origen natural": "Evento Catastrófico Natural",
    "Enfermedad profesional": "Enfermedad Profesional",
}

BED_GROUP_MAP = {  # nombre legible y consistente del servicio
    "URGENCIAS": "Urgencias",
    "HOSPITALIZACION": "Hospitalización Adultos",
    "PEDIATRIA": "Pediatría",
    "RECUPERACION": "Recuperación (post-quirúrgico)",
    "GINECO OBSTRETICIA": "Gineco-obstetricia",
    "UNIDAD DE CUIDADO BASICO": "Cuidado Básico Neonatal",
    "UNIDAD DE CUIDADO INTERMEDIO": "Cuidado Intermedio",
    "UNIDAD DE CUIDADO INTENSIVO": "UCI",
    "SALA PARTOS": "Sala de Partos",
}


def build_admissions(raw, patients):
    i = read_raw(raw, "Ingresos")
    adm_at = to_dt(i.FechaIngreso)
    birth = pd.to_datetime(i.IdPaciente.astype(int).map(patients.set_index("patient_id").birth_date))
    out = pd.DataFrame({
        "admission_id": i.OidIngreso.astype(int),
        "admission_number": i.ConsecutivoIngreso.astype(int),
        "patient_id": i.IdPaciente.astype(int),
        "admission_class": i.ClaseIngreso,          # Ambulatorio = urgencias sin hospitalizar
        "admission_route": i.ViaIngreso,
        "risk_type": i.TipoRiesgo.replace(RISK_MAP),
        "admission_at": fmt_dt(adm_at),
        "hospitalization_at": fmt_dt(to_dt(i.FechaHospitalizacion)),
        "triage_id": pd.to_numeric(i.OidTriageA, errors="coerce").astype("Int64"),
        "bed_code": i.CodigoCama,
        "bed_name": clean_text(i.NombreCama),
        "is_virtual_bed": i.NombreCama.str.contains("VIRTUAL", na=False).astype(int),
        "service": i.NombreGrupoCama.map(BED_GROUP_MAP).fillna(i.NombreGrupoCama),
        "sub_service": clean_text(i.NombreSubgrupoCama),
        "diagnosis_code": i.CodigoDiagnostico,
        "diagnosis_name": clean_text(i.NombreDiagnostico),
        "diagnosis_chapter": i.CodigoDiagnostico.str[0],  # letra CIE-10 (J=respiratorio, O=embarazo, S/T=trauma...)
        "age_years": ((adm_at - birth).dt.days / 365.25).round(1),
    })
    out["age_group"] = pd.cut(out.age_years, [-1, 1, 5, 18, 60, 200],
                              labels=["<1 año", "1-4", "5-17", "18-59", "60+"]).astype(str)
    return out


# ---------------------------------------------------------------- atención
def build_first_care(raw):
    a = read_raw(raw, "Atencion")
    return pd.DataFrame({"admission_id": a.OidIngreso.astype(int),
                         "first_care_at": fmt_dt(to_dt(a.FechaAtencion))})


# ---------------------------------------------------------------- servicios
def build_services(raw):
    s = read_raw(raw, "Servicios")
    return pd.DataFrame({
        "line_id": s.OidS.astype(int),
        "admission_id": s.OidIngreso.astype(int),
        "service_code": s.CodigoServicio,
        "service_name": clean_text(s.NombreServicio),
        "quantity": s.Cantidad.astype(int),
        "performed_at": fmt_dt(to_dt(s.FechaPrestacion)),
        "area_code": s.CodigoAreaServicio,
        "area": clean_text(s.AreaServicio),
        "specialty": clean_text(s.Especialidad),
    })


# ---------------------------------------------------------------- medicamentos
ATC = re.compile(r"^[A-Z]\d{2}[A-Z]{2}")  # códigos de medicamento tipo ATC (p.ej. B05BM002702)


def build_medications(raw):
    m = read_raw(raw, "MedicamentoInsumo")
    code = m.CodigoServicio.str.strip()
    return pd.DataFrame({
        "line_id": m.OidMI.astype(int),
        "admission_id": m.OidIngreso.astype(int),
        "item_code": code,
        "item_name": clean_text(m.NombreServicio),
        "item_type": np.where(code.str.match(ATC), "Medicamento", "Dispositivo/Insumo"),
        "quantity": m.Cantidad.astype(int),
        "dispensed_at": fmt_dt(to_dt(m.FechaPrestacion)),
        "area": clean_text(m.AreaServicio),
        "specialty": clean_text(m.Especialidad),
    })


# ---------------------------------------------------------------- cirugías
def build_surgery(raw, admissions, services):
    c = read_raw(raw, "ProgramacionCirugia")
    out = pd.DataFrame({
        "schedule_id": c.ConsecutivoProgramacion.astype(np.int64),  # quita ceros a la izquierda
        "patient_id": c.IdPaciente.astype(int),
        "admission_id": pd.to_numeric(c.OidIngreso, errors="coerce").astype("Int64"),
        "procedure_code": c.CodigoServicio.str.strip(),
    })
    valid = set(admissions.admission_id)
    out["in_dataset"] = out.admission_id.isin(valid).astype(int)  # solo ~31% cruza con Ingresos
    billed = set(zip(services.admission_id, services.service_code))
    out["was_billed"] = [int((a, p) in billed) if pd.notna(a) else 0
                         for a, p in zip(out.admission_id, out.procedure_code)]
    return out


# ---------------------------------------------------------------- derivadas
STAY_UNIT_RULES = [  # orden importa
    ("INTENSIVO NEONATAL", "UCI Neonatal"),
    ("INTENSIVO PEDI", "UCI Pediátrica"),
    ("INTENSIVO ADULTO", "UCI Adultos"),
    ("INTERMEDIO NEONATAL", "Intermedio Neonatal"),
    ("INTERMEDIO PEDI", "Intermedio Pediátrico"),
    ("INTERMEDIO ADULTO", "Intermedio Adultos"),
    ("BÁSICO NEONATAL", "Básico Neonatal"),
    ("BASICO NEONATAL", "Básico Neonatal"),
    ("PEDIÁTRICA", "Hospitalización Pediátrica"),
    ("PEDIATRICA", "Hospitalización Pediátrica"),
    ("ADULTOS", "Hospitalización Adultos"),
]


def stay_unit(name: str) -> str:
    u = name.upper()
    for key, unit in STAY_UNIT_RULES:
        if key in u:
            return unit
    return "Otra internación"


def build_stays(services):
    """Líneas INTERNACIÓN de Servicios: quantity = días de estancia, performed_at = inicio."""
    st = services[services.service_name.str.upper().str.contains("INTERNACI")].copy()
    start = pd.to_datetime(st.performed_at)
    return pd.DataFrame({
        "admission_id": st.admission_id,
        "unit": st.service_name.map(stay_unit),
        "start_at": fmt_dt(start),
        "days": st.quantity,
        "end_at_estimated": fmt_dt(start + pd.to_timedelta(st.quantity, unit="D")),
    })


def add_episode_times(admissions, services, meds):
    """Egreso estimado = última actividad registrada (servicio o medicamento) del ingreso.
    Validado: la estancia facturada (INTERNACIÓN) no sirve para 'hoy' porque se cobra al egreso."""
    last = pd.concat([
        services[["admission_id", "performed_at"]].rename(columns={"performed_at": "t"}),
        meds[["admission_id", "dispensed_at"]].rename(columns={"dispensed_at": "t"}),
    ]).groupby("admission_id").t.max()
    start = pd.to_datetime(admissions.hospitalization_at.fillna(admissions.admission_at))
    end = pd.to_datetime(admissions.admission_id.map(last)).fillna(start)
    end = pd.concat([start, end], axis=1).max(axis=1)
    admissions["last_activity_at"] = fmt_dt(end)
    admissions["length_of_stay_days"] = ((end - start).dt.total_seconds() / 86400).round(2)
    return admissions


def build_bed_census(admissions):
    """Pacientes presentes por día y servicio (corte 12:00 m.).
    Servicio = cama registrada en el ingreso (para episodios abiertos es la cama actual)."""
    a = admissions.copy()
    a["start"] = pd.to_datetime(a.hospitalization_at.fillna(a.admission_at))
    a["end"] = pd.to_datetime(a.last_activity_at)
    days = pd.date_range(a.start.min().normalize(), a.end.max().normalize(), freq="D") + pd.Timedelta(hours=12)
    rows = []
    for service, g in a.groupby("service"):
        s, e = g.start.values, g.end.values
        for d in days:
            dv = np.datetime64(d)
            rows.append((d.strftime("%Y-%m-%d"), service, int(((s <= dv) & (e >= dv)).sum())))
    return pd.DataFrame(rows, columns=["census_date", "service", "occupied_beds"])


def build_bed_capacity(admissions):
    """Capacidad ESTIMADA = camas distintas usadas en el periodo. Las camas 'VIRTUAL' son
    expansión (sobreocupación). Reemplazar por capacidad real si el hospital la entrega."""
    g = admissions.groupby("service")
    cap = pd.DataFrame({
        "capacity_beds": g.bed_code.nunique(),
        "physical_beds": g.apply(lambda x: x.loc[x.is_virtual_bed == 0, "bed_code"].nunique()),
    }).reset_index()
    cap["is_estimated"] = 1
    return cap


def build_wait_times(admissions, triage, first_care):
    w = (admissions[["admission_id", "service", "admission_at", "triage_id"]]
         .dropna(subset=["triage_id"])
         .merge(triage[["triage_id", "triage_at", "triage_level", "triage_area"]], on="triage_id")
         .merge(first_care, on="admission_id"))
    mins = (pd.to_datetime(w.first_care_at) - pd.to_datetime(w.triage_at)).dt.total_seconds() / 60
    w["wait_minutes"] = mins.round(1)
    w = w[(w.wait_minutes >= 0) & (w.wait_minutes <= 24 * 60)]  # descarta registros imposibles
    return w[["admission_id", "service", "triage_level", "triage_area",
              "triage_at", "first_care_at", "wait_minutes"]]


def build_drug_inventory(meds, reference_date):
    """SIMULADO: los datos no traen stock ni vencimiento. Se genera a partir del
    consumo real (promedio diario de los últimos 30 días) con semilla fija."""
    rng = np.random.default_rng(SEED)
    m = meds[meds.item_type == "Medicamento"].copy()
    m["d"] = pd.to_datetime(m.dispensed_at)
    ref = pd.Timestamp(reference_date)
    recent = m[m.d > ref - pd.Timedelta(days=30)]
    daily = recent.groupby(["item_code", "item_name"]).quantity.sum().div(30).reset_index(name="avg_daily_consumption")
    daily = daily[daily.avg_daily_consumption > 0]
    days_cover = np.where(rng.random(len(daily)) < 0.12, rng.uniform(0.5, 5, len(daily)),
                          rng.uniform(6, 60, len(daily)))  # ~12% en riesgo (<5 días)
    daily["stock_units"] = np.ceil(daily.avg_daily_consumption * days_cover).astype(int)
    daily["days_of_inventory"] = (daily.stock_units / daily.avg_daily_consumption).round(1)
    daily["avg_daily_consumption"] = daily.avg_daily_consumption.round(2)
    daily["expiry_date"] = [(ref + pd.Timedelta(days=int(x))).strftime("%Y-%m-%d")
                            for x in rng.integers(15, 720, len(daily))]
    daily["is_simulated"] = 1
    return daily


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="carpeta con los .txt crudos")
    ap.add_argument("--out", default="data/hospital.db")
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    print("Leyendo y limpiando...")
    patients = build_patients(raw)
    triage = build_triage(raw)
    admissions = build_admissions(raw, patients)
    first_care = build_first_care(raw)
    services = build_services(raw)
    meds = build_medications(raw)
    surgery = build_surgery(raw, admissions, services)
    reference_date = pd.to_datetime(admissions.admission_at).max().strftime("%Y-%m-%d")

    print("Construyendo tablas derivadas...")
    admissions = add_episode_times(admissions, services, meds)
    stays = build_stays(services)
    census = build_bed_census(admissions)
    capacity = build_bed_capacity(admissions)
    waits = build_wait_times(admissions, triage, first_care)
    inventory = build_drug_inventory(meds, reference_date)
    meta = pd.DataFrame([
        ("reference_date", reference_date, "Fecha que el sistema trata como 'hoy'"),
        ("data_start", pd.to_datetime(admissions.admission_at).min().strftime("%Y-%m-%d"), "Inicio del extracto"),
        ("inventory_note", "simulado", "drug_inventory es simulado a partir del consumo real"),
        ("capacity_note", "estimado", "bed_capacity = camas distintas usadas por servicio (physical_beds excluye virtuales)"),
        ("census_note", "estimado", "bed_census_daily = pacientes entre hospitalización y última actividad, corte 12:00"),
    ], columns=["key", "value", "description"])

    tables = dict(patients=patients, triage=triage, admissions=admissions, first_care=first_care,
                  services=services, medications=meds, surgery_schedule=surgery, stays=stays,
                  bed_census_daily=census, bed_capacity=capacity, wait_times=waits,
                  drug_inventory=inventory, dataset_meta=meta)

    con = sqlite3.connect(out)
    for name, df in tables.items():
        df.to_sql(name, con, index=False)
        print(f"  {name:18s} {len(df):>8,} filas")

    con.executescript("""
    CREATE INDEX ix_adm_patient ON admissions(patient_id);
    CREATE INDEX ix_adm_date ON admissions(admission_at);
    CREATE INDEX ix_adm_service ON admissions(service);
    CREATE INDEX ix_srv_adm ON services(admission_id);
    CREATE INDEX ix_srv_date ON services(performed_at);
    CREATE INDEX ix_med_adm ON medications(admission_id);
    CREATE INDEX ix_med_item ON medications(item_code);
    CREATE INDEX ix_med_date ON medications(dispensed_at);
    CREATE INDEX ix_census ON bed_census_daily(census_date, service);
    CREATE INDEX ix_wait ON wait_times(triage_at);

    -- Vista segura para el agente: sin diagnóstico específico ni ids de paciente
    CREATE VIEW v_admissions_safe AS
    SELECT admission_id, admission_class, admission_route, risk_type, admission_at,
           hospitalization_at, last_activity_at, length_of_stay_days,
           service, sub_service, diagnosis_chapter, age_group
    FROM admissions;

    -- Ocupación diaria con porcentaje
    CREATE VIEW v_occupancy_daily AS
    SELECT c.census_date, c.service, c.occupied_beds, k.capacity_beds, k.physical_beds,
           ROUND(100.0 * c.occupied_beds / k.capacity_beds, 1) AS occupancy_pct,
           ROUND(100.0 * c.occupied_beds / NULLIF(k.physical_beds, 0), 1) AS occupancy_physical_pct
    FROM bed_census_daily c JOIN bed_capacity k USING(service);
    """)
    con.commit()
    con.close()
    print(f"Listo: {out}  (hoy = {reference_date})")


if __name__ == "__main__":
    main()
