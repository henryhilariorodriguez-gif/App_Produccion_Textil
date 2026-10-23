import os
import pandas as pd
import pyodbc

# ============================================================
# DIAS QUE SE VAN A AGREGAR (ambos incluidos)
# ============================================================

FECHA_DESDE = "2026-10-17"
FECHA_HASTA = "2026-10-21"

# ============================================================
# ARCHIVOS EXCEL, HOJAS Y TABLAS DE DESTINO (igual que migrar_excel.py)
# ============================================================

FUENTES = [
    {
        "archivo": r"C:\Users\crexs\OneDrive\Escritorio\migracion\TINTORERIA.xlsm",
        "hoja": "PRODUCCION",
        "tabla": "Raw_Tintoreria",
        "columnas": [
            "Fecha", "MQ", "Operario", "Partida", "Rollos", "Peso",
            "Articulo", "Color", "CodColor", "HInicio", "HFin",
            "Cliente", "Tiempo", "Observaciones"
        ]
    },
    {
        "archivo": r"C:\Users\crexs\OneDrive\Escritorio\migracion\prueba_respaldo.xlsx",
        "hoja": "INGRESO",
        "tabla": "Raw_Areas",
        "columnas": [
            "Fecha", "Turno", "Area", "Maq", "Operario", "Partida",
            "Color", "Articulo", "Rollos", "Kilos", "Cliente",
            "HInicio", "HFin", "Observaciones"
        ]
    },
    {
        "archivo": r"C:\Users\crexs\OneDrive\Escritorio\migracion\TINTORERIA.xlsm",
        "hoja": "RECETAS 2026",
        "tabla": "Raw_Recetas",
        "columnas": [
            "Fecha", "Partida", "Color", "Cod", "Cliente",
            "Articulo", "Rollos", "Kilos"
        ]
    }
]

CADENA_CONEXION = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=localhost\SQLEXPRESS;"
    "DATABASE=ProduccionTextil;"
    "Trusted_Connection=yes;"
)


# ============================================================
# LEER EL EXCEL Y QUEDARSE SOLO CON LOS DIAS PEDIDOS
# ============================================================

def preparar_datos(origen):
    archivo = origen["archivo"]
    hoja = origen["hoja"]
    columnas = origen["columnas"]
    tabla = origen["tabla"]

    print(f"\nLeyendo: {os.path.basename(archivo)} | hoja {hoja} -> {tabla}")

    if not os.path.isfile(archivo):
        raise FileNotFoundError(f"No se encuentra el archivo:\n{archivo}")

    df = pd.read_excel(
        archivo,
        sheet_name=hoja,
        dtype=str,
        keep_default_na=False,
        usecols=list(range(len(columnas)))
    )

    if df.shape[1] != len(columnas):
        raise ValueError(
            f"La hoja {hoja} tiene {df.shape[1]} columnas "
            f"seleccionadas; se esperaban {len(columnas)}."
        )

    df.columns = columnas

    # Numero de fila en Excel (la fila 1 es el encabezado), igual que antes.
    df["_fila"] = range(2, len(df) + 2)

    texto_fecha = df["Fecha"].astype(str).str.strip()
    fechas = pd.to_datetime(texto_fecha, errors="coerce")
    ilegibles = int((fechas.isna() & (texto_fecha != "")).sum())

    desde = pd.Timestamp(FECHA_DESDE)
    hasta = pd.Timestamp(FECHA_HASTA) + pd.Timedelta(days=1)
    en_rango = (fechas >= desde) & (fechas < hasta)

    df = df[en_rango]
    fechas = fechas[en_rango]

    print("Filas por dia:")
    cuenta = fechas.dt.date.value_counts().sort_index()
    for dia, n in cuenta.items():
        print(f"   {dia}: {n}")
    if cuenta.empty:
        print("   (no hay filas en ese rango)")
    if ilegibles:
        print(f"AVISO: {ilegibles} filas con fecha ilegible; no se incluyen.")

    filas = []
    for _, fila in df.iterrows():
        valores = []
        for col in columnas:
            texto = str(fila[col]).strip()
            valores.append(None if texto == "" else texto)

        if all(v is None for v in valores):
            continue

        filas.append(tuple(valores + [int(fila["_fila"])]))

    print(f"Filas a agregar: {len(filas)}")
    return filas


# ============================================================
# AGREGAR A SQL SERVER (SIN VACIAR LAS TABLAS)
# ============================================================

def agregar():
    conn = None

    try:
        print("=" * 55)
        print(f"AGREGAR DIAS {FECHA_DESDE} AL {FECHA_HASTA}")
        print("=" * 55)

        datos = []
        for origen in FUENTES:
            datos.append((origen, preparar_datos(origen)))

        print("\nTodavia no se ha modificado SQL Server.")
        print("Se agregaran SOLO esos dias a las tablas Raw.")
        print("Lo que ya esta cargado de otros dias no se toca.")
        print("\nEscribe AGREGAR para continuar.")

        if input("> ").strip() != "AGREGAR":
            print("\nCancelado. No se modifico SQL Server.")
            return

        conn = pyodbc.connect(CADENA_CONEXION)
        cursor = conn.cursor()
        cursor.fast_executemany = True

        for origen, filas in datos:
            tabla = origen["tabla"]
            columnas = origen["columnas"]

            # Si el script se corrio antes, se borran solo esos dias
            # para no duplicar filas.
            cursor.execute(
                f"DELETE FROM dbo.[{tabla}] "
                f"WHERE TRY_CONVERT(date, [Fecha]) >= ?",
                FECHA_DESDE
            )

            nombres = ", ".join(f"[{c}]" for c in columnas)
            marcadores = ", ".join("?" for _ in range(len(columnas) + 1))
            consulta = (
                f"INSERT INTO dbo.[{tabla}] ({nombres}, [FilaExcel]) "
                f"VALUES ({marcadores})"
            )

            if filas:
                cursor.executemany(consulta, filas)

            print(f"{tabla}: {len(filas)} filas agregadas.")

        # Las tres tablas se confirman juntas.
        conn.commit()

        print("\nComo quedaron las tablas Raw:")
        for origen, _ in datos:
            tabla = origen["tabla"]
            cursor.execute(
                f"SELECT COUNT(*), MAX(TRY_CONVERT(date, [Fecha])) "
                f"FROM dbo.[{tabla}]"
            )
            total, ultima = cursor.fetchone()
            print(f"   {tabla}: {total} filas, ultima fecha {ultima}")

        print("\nLISTO.")

    except Exception as error:
        if conn is not None:
            conn.rollback()
        print("\nERROR. Se revirtio todo; SQL Server quedo como estaba.")
        print(f"Detalle: {error}")

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    agregar()