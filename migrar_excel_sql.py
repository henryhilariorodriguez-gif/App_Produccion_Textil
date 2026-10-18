
import os
import pandas as pd
import pyodbc

# ============================================================
# 1. ARCHIVOS EXCEL, HOJAS Y TABLAS DE DESTINO
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

# ============================================================
# 2. CONEXION A SQL SERVER
# ============================================================

CADENA_CONEXION = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=localhost\SQLEXPRESS;"
    "DATABASE=ProduccionTextil;"
    "Trusted_Connection=yes;"
)

# ============================================================
# 3. LEER Y VALIDAR LOS ARCHIVOS
# ============================================================

def preparar_datos(origen):
    archivo = origen["archivo"]
    hoja = origen["hoja"]
    columnas = origen["columnas"]
    tabla = origen["tabla"]

    print(f"\nLeyendo archivo: {os.path.basename(archivo)}")
    print(f"Hoja: {hoja}")
    print(f"Destino: {tabla}")

    if not os.path.isfile(archivo):
        raise FileNotFoundError(
            f"No se encuentra el archivo:\n{archivo}"
        )

    # Leer Excel conservando los valores como texto.
    # No se modifica el archivo original.
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

    filas = []

    for fila_excel, fila in enumerate(
        df.itertuples(index=False, name=None),
        start=2
    ):
        valores = []

        for valor in fila:
            texto = str(valor).strip()

            if texto == "":
                valores.append(None)
            else:
                valores.append(texto)

        # Ignorar filas completamente vacías.
        if all(valor is None for valor in valores):
            continue

        # Guardar también el número de fila de Excel.
        filas.append(tuple(valores + [fila_excel]))

    print(f"Filas encontradas: {len(filas)}")

    return filas


# ============================================================
# 4. CARGAR LOS DATOS EN SQL SERVER
# ============================================================

def migrar():
    conn = None

    try:
        print("=" * 55)
        print("MIGRACION EXCEL -> SQL SERVER")
        print("=" * 55)

        # Primero preparar y validar los tres Excel.
        # Todavía no se modifica SQL Server.
        datos_preparados = []

        for origen in FUENTES:
            filas = preparar_datos(origen)
            datos_preparados.append((origen, filas))

        print("\nArchivos leídos correctamente.")
        print("\nATENCION:")
        print("La siguiente operación reemplazará los datos")
        print("existentes en las tres tablas Raw.")
        print("Las tablas de producción definitivas no se modifican.")
        print("\nEscribe REEMPLAZAR para continuar.")

        confirmacion = input("> ").strip()

        if confirmacion != "REEMPLAZAR":
            print("\nOperación cancelada. No se modificó SQL Server.")
            return

        conn = pyodbc.connect(CADENA_CONEXION)
        cursor = conn.cursor()
        cursor.fast_executemany = True

        total_general = 0

        # La carga se ejecuta dentro de una sola transacción.
        # Si falla una tabla, se revierte toda la operación.
        for origen, filas in datos_preparados:
            tabla = origen["tabla"]
            columnas = origen["columnas"]

            print(f"\nPreparando tabla {tabla}...")

            # Vaciar solamente la tabla Raw correspondiente.
            cursor.execute(f"TRUNCATE TABLE dbo.[{tabla}]")

            nombres_columnas = ", ".join(
                f"[{columna}]" for columna in columnas
            )

            marcadores = ", ".join(
                "?" for _ in range(len(columnas) + 1)
            )

            consulta = (
                f"INSERT INTO dbo.[{tabla}] "
                f"({nombres_columnas}, [FilaExcel]) "
                f"VALUES ({marcadores})"
            )

            if filas:
                cursor.executemany(consulta, filas)

            print(f"{tabla}: {len(filas)} filas procesadas.")
            total_general += len(filas)

        # Confirmar las tres cargas juntas.
        conn.commit()

        print("\n" + "=" * 55)
        print("MIGRACION COMPLETADA CORRECTAMENTE")
        print(f"Total de filas cargadas: {total_general}")
        print("=" * 55)

    except Exception as error:
        if conn is not None:
            conn.rollback()

        print("\nERROR DURANTE LA MIGRACION")
        print("Se intentó revertir la transacción de SQL Server.")
        print(f"Detalle: {error}")

    finally:
        if conn is not None:
            conn.close()


# ============================================================
# 5. EJECUTAR
# ============================================================

if __name__ == "__main__":
    migrar()
