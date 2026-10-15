from flask import Flask, render_template, request, redirect
import pyodbc

app = Flask(__name__)


# -------------------------------
# CONEXIÓN A SQL SERVER
# -------------------------------
conn = pyodbc.connect(
    'DRIVER={ODBC Driver 17 for SQL Server};'
    'SERVER=localhost\\SQLEXPRESS;'
    'DATABASE=ProduccionTextil;'
    'Trusted_Connection=yes;'
)
cursor = conn.cursor()

# Áreas del menú (cada una agrupa uno o más procesos de la Hoja de Ruta)
AREAS = {
    'Recepción': ['Recepción'],
    'Preparado': ['Preparado', 'Preparado crudo'],
    'Teñido': ['Teñido'],
    'Termofijado': ['Termofijado'],
    'Hidrocentrifugado': ['Hidrocentrifugado'],
    'Secado': ['Secado'],
    'Volteados': ['Volteado crudo', 'Volteado termofijado', 'Volteado para perchadora',
                  'Volteado color', 'Volteado perchado', 'Volteado teñido'],
    'Perchado': ['Perchado'],
    'Compactado': ['Compactado'],
    'Embolsado': ['Embolsado'],
    'Pesado': ['Pesado'],
    'Despacho': ['Despacho'],
}

# Hace que el menú esté disponible en todas las plantillas
@app.context_processor
def datos_menu():
    return {'areas_menu': list(AREAS.keys())}

SQL_PARTIDAS = """
    SELECT
        p.NumeroPartida, p.Cliente, p.Color, p.Rollos, p.Kilos,
        p.ProcesoActual, p.Estado, p.Articulo, p.CodigoCrudo,
        (
            SELECT TOP 1 h2.Proceso
            FROM Articulos a
            INNER JOIN HojaRuta h2 ON h2.Articulo = a.RutaArticulo
            WHERE a.Nombre = p.Articulo
              AND h2.Orden > (
                  SELECT h1.Orden FROM HojaRuta h1
                  WHERE h1.Articulo = a.RutaArticulo
                    AND h1.Proceso = p.ProcesoActual
              )
            ORDER BY h2.Orden
        ) AS SiguienteProceso
    FROM Partidas p
"""

# -------------------------------
# INICIO
# -------------------------------
@app.route('/inicio')
def inicio():
    cursor.execute("""
        SELECT
            SUM(CASE WHEN ISNULL(Estado,'') <> 'Finalizada' THEN 1 ELSE 0 END),
            SUM(CASE WHEN Estado = 'Pendiente de reproceso' THEN 1 ELSE 0 END),
            SUM(CASE WHEN Estado = 'Finalizada' THEN 1 ELSE 0 END)
        FROM Partidas
    """)
    activas, pendientes, despachadas = cursor.fetchone()
    return render_template('inicio.html',
                           activas=activas or 0,
                           pendientes=pendientes or 0,
                           despachadas=despachadas or 0)

# -------------------------------
# PARTIDAS DE UN ÁREA
# -------------------------------
@app.route('/area/<nombre>')
def area(nombre):
    procesos = AREAS.get(nombre)
    if procesos is None:
        return "Área no encontrada."
    marcadores = ','.join('?' * len(procesos))
    cursor.execute(SQL_PARTIDAS + f" WHERE p.ProcesoActual IN ({marcadores})", tuple(procesos))
    partidas = cursor.fetchall()
    return render_template('index.html', partidas=partidas, titulo=nombre)

# -------------------------------
# LISTADO DE PARTIDAS
# -------------------------------
@app.route('/')
def index():

    cursor.execute("""
        SELECT
            p.NumeroPartida,
            p.Cliente,
            p.Color,
            p.Rollos,
            p.Kilos,
            p.ProcesoActual,
            p.Estado,
            p.Articulo,
            p.CodigoCrudo,
            (
                SELECT TOP 1 h2.Proceso
                FROM Articulos a
                INNER JOIN HojaRuta h2
                    ON h2.Articulo = a.RutaArticulo
                WHERE a.Nombre = p.Articulo
                  AND h2.Orden > (
                      SELECT h1.Orden
                      FROM HojaRuta h1
                      WHERE h1.Articulo = a.RutaArticulo
                        AND h1.Proceso = p.ProcesoActual
                  )
                ORDER BY h2.Orden
            ) AS SiguienteProceso
        FROM Partidas p
    """)

    partidas = cursor.fetchall()

    return render_template('index.html', partidas=partidas)

#--------------------------------
#REGISTRA EL SIGUIENTE PROCESO
#--------------------------------
@app.route('/avanzar/<numero>', methods=['GET', 'POST'])
def avanzar(numero):

    # Buscar la partida
    cursor.execute("""
        SELECT
            NumeroPartida,
            Articulo,
            ProcesoActual,
            Estado,
            ProcesoReproceso,
            MotivoReproceso,
            SupervisorReproceso
        FROM Partidas
        WHERE NumeroPartida = ?
    """, (numero,))

    partida = cursor.fetchone()

    print("PARTIDA:", partida)

    if partida is None:
        return "Partida no encontrada."
    
    if partida[3] == 'Finalizada':
        return "Esta partida ya está finalizada."


    # CAMBIO 3: primero se revisa si hay un reproceso pendiente.
    # Antes, si la partida estaba en el último paso de su Hoja de Ruta,
    # respondía "ya completó" y el reproceso quedaba trabado.
    if partida[3] == 'Pendiente de reproceso':

        # Usar el proceso indicado por el supervisor
        siguiente_proceso = partida[4]

    else:

        # Buscar el siguiente proceso en la Hoja de Ruta
        cursor.execute("""
            SELECT TOP 1
                h.Proceso
            FROM Partidas p
            INNER JOIN Articulos a
                ON a.Nombre = p.Articulo
            INNER JOIN HojaRuta h
                ON h.Articulo = a.RutaArticulo
            WHERE p.NumeroPartida = ?
              AND h.Orden > (
                  SELECT h2.Orden
                  FROM HojaRuta h2
                  WHERE h2.Articulo = a.RutaArticulo
                    AND h2.Proceso = p.ProcesoActual
              )
            ORDER BY h.Orden
        """, (numero,))

        siguiente = cursor.fetchone()

        if siguiente is None:
            return "La partida ya completó su Hoja de Ruta."

        siguiente_proceso = siguiente[0]
        
    # Solo se pueden omitir los volteados, y no cuando es un reproceso
    es_volteado = siguiente_proceso.lower().startswith('volteado')
    puede_omitir = es_volteado and partida[3] != 'Pendiente de reproceso'    


    # Si el supervisor confirma
    if request.method == 'POST':
        
        if request.form.get('accion') == 'omitir':

            if not puede_omitir:
                return "Este paso no se puede omitir."

            cursor.execute("""
                INSERT INTO Procesos
                (
                    NumeroPartida,
                    NombreProceso,
                    FechaInicio,
                    OperarioID,
                    MaquinaID,
                    TipoProceso
                )
                VALUES (?, ?, GETDATE(), NULL, NULL, 'Omitido')
            """, (numero, siguiente_proceso))

            cursor.execute("""
                UPDATE Partidas
                SET ProcesoActual = ?
                WHERE NumeroPartida = ?
            """, (siguiente_proceso, numero))

            conn.commit()

            return redirect('/')
        
        operario = request.form.get('operario')
        maquina = request.form.get('maquina') or None

        if not operario:
            return "Falta seleccionar el operario."

        if maquina is None:
            return "Falta seleccionar la máquina."


        # Verificar que este proceso todavía no haya sido registrado
        # (solo cuenta lo registrado después del último reproceso)
        if partida[3] != 'Pendiente de reproceso':

            cursor.execute("""
                SELECT COUNT(*)
                FROM Procesos
                WHERE NumeroPartida = ?
                  AND NombreProceso = ?
                  AND TipoProceso = 'Normal'
                  AND ProcesoID > ISNULL((
                      SELECT MAX(ProcesoID)
                      FROM Procesos
                      WHERE NumeroPartida = ?
                        AND TipoProceso = 'Reproceso'
                  ), 0)
            """, (numero, siguiente_proceso, numero))

            proceso_existente = cursor.fetchone()[0]

            if proceso_existente > 0:
                return "Este proceso ya fue registrado para esta partida."

        print("=== INICIANDO REGISTRO ===")
        print("PARTIDA:", numero)
        print("PROCESO:", siguiente_proceso)
        print("ESTADO:", partida[3])
        print("OPERARIO:", operario)
        print("MAQUINA:", maquina)

        # Registrar el proceso
        # CAMBIO 1: ahora se guarda en MaquinaID (antes en Maquina),
        # que es la columna que lee /supervisor_tintoreria.
        cursor.execute("""
            INSERT INTO Procesos
            (
                NumeroPartida,
                NombreProceso,
                FechaInicio,
                OperarioID,
                MaquinaID,
                TipoProceso,
                MotivoReproceso,
                SupervisorReproceso
            )
            VALUES (?, ?, GETDATE(), ?, ?, ?, ?, ?)
        """, (
            numero,
            siguiente_proceso,
            operario,
            maquina,
            'Reproceso' if partida[3] == 'Pendiente de reproceso' else 'Normal',
            partida[5] if partida[3] == 'Pendiente de reproceso' else None,
            partida[6] if partida[3] == 'Pendiente de reproceso' else None
        ))


        # Actualizar la partida
        if partida[3] == 'Pendiente de reproceso':

            cursor.execute("""
                UPDATE Partidas
                SET
                    ProcesoActual = ?,
                    Estado = 'En proceso',
                    ProcesoReproceso = NULL,
                    MotivoReproceso = NULL,
                    SupervisorReproceso = NULL
                WHERE NumeroPartida = ?
            """, (siguiente_proceso, numero))

        else:

            # ¿Este proceso es el último de la Hoja de Ruta del artículo?
            cursor.execute("""
                SELECT CASE
                    WHEN h.Orden = (
                        SELECT MAX(Orden)
                        FROM HojaRuta
                        WHERE Articulo = a.RutaArticulo
                    ) THEN 1 ELSE 0 END
                FROM Articulos a
                INNER JOIN HojaRuta h
                    ON h.Articulo = a.RutaArticulo
                WHERE a.Nombre = ?
                  AND h.Proceso = ?
            """, (partida[1], siguiente_proceso))

            fila = cursor.fetchone()
            es_ultimo = bool(fila and fila[0] == 1)

            cursor.execute("""
                UPDATE Partidas
                SET ProcesoActual = ?,
                    Estado = ?
                WHERE NumeroPartida = ?
            """, (
                siguiente_proceso,
                'Finalizada' if es_ultimo else partida[3],
                numero
            ))


        conn.commit()

        return redirect('/')


    # Buscar operarios activos
    cursor.execute("""
        SELECT
            OperarioID,
            Nombre
        FROM Operarios
        WHERE Activo = 1
        ORDER BY Nombre
    """)

    operarios = cursor.fetchall()


    # Buscar máquinas activas
    cursor.execute("""
        SELECT
            MaquinaID,
            Nombre
        FROM Maquinas
        WHERE Activo = 1
        ORDER BY Nombre
    """)

    maquinas = cursor.fetchall()


    return render_template(
        'confirmar_proceso.html',
        partida=partida,
        siguiente_proceso=siguiente_proceso,
        operarios=operarios,
        maquinas=maquinas,
        puede_omitir=puede_omitir
    )
# -------------------------------
# REGISTRAR ALGUN REPROCESO
# -------------------------------
@app.route('/reprocesar/<numero>', methods=['GET', 'POST'])
def reprocesar(numero):

    # Buscar la partida
    cursor.execute("""
        SELECT
            NumeroPartida,
            Articulo,
            ProcesoActual
        FROM Partidas
        WHERE NumeroPartida = ?
    """, (numero,))

    partida = cursor.fetchone()

    if partida is None:
        return "Partida no encontrada."

    # Buscar la Hoja de Ruta del artículo
    cursor.execute("""
        SELECT
            h.Proceso
        FROM Articulos a
        INNER JOIN HojaRuta h
            ON h.Articulo = a.RutaArticulo
        WHERE a.Nombre = ?
        ORDER BY h.Orden
    """, (partida[1],))

    procesos = cursor.fetchall()
    if request.method == 'POST':

        proceso_reproceso = request.form['proceso_reproceso']
        motivo = request.form['motivo']
        supervisor = request.form['supervisor']

        # Si el motivo es "Otro", usar el texto escrito
        if motivo == 'Otro':
            motivo = request.form['motivo_otro']

        print(proceso_reproceso, motivo, supervisor)

        # Guardar la solicitud de reproceso
        # CAMBIO 2: se quitó el UPDATE repetido que había aquí.
        cursor.execute("""
            UPDATE Partidas
            SET
                Estado = 'Pendiente de reproceso',
                ProcesoReproceso = ?,
                MotivoReproceso = ?,
                SupervisorReproceso = ?
            WHERE NumeroPartida = ?
        """, (
            proceso_reproceso,
            motivo,
            supervisor,
            numero
        ))

        conn.commit()

        return redirect('/')
    return render_template(
        'reprocesar.html',
        partida=partida,
        procesos=procesos
    )


# -------------------------------
# REGISTRAR NUEVA PARTIDA
# -------------------------------
@app.route('/nueva_partida', methods=['GET', 'POST'])
def nueva_partida():
    if request.method == 'POST':
        documento = request.form['documento']
        numero = request.form['numero']
        cliente = request.form['cliente']
        color = request.form['color']
        codcolor = request.form['codcolor']
        rollos = request.form['rollos']
        kilos = request.form['kilos']
        peso = request.form['peso']
        articulo = request.form['articulo']
        proceso = request.form['proceso']
        estado = request.form['estado']

        cursor.execute("""
            INSERT INTO Partidas 
            (NumeroDocumento, NumeroPartida, Cliente, Color, CodColor, Rollos, Kilos, ProcesoActual, Estado, Articulo) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (documento, numero, cliente, color, codcolor, rollos, kilos, proceso, estado, articulo))
        
        cursor.execute("""
             SELECT TOP 1 ProcesoID
             FROM Procesos
             WHERE NumeroPartida = ?
               AND NombreProceso = 'Recepción'
             ORDER BY ProcesoID DESC
        """, (numero,))

        proceso_id = cursor.fetchone()[0]

        cursor.execute("""
             UPDATE Procesos
             SET Peso = ?
             WHERE ProcesoID = ?
        """, (peso, proceso_id))

        conn.commit()

        return redirect('/')

    cursor.execute("""
        SELECT Nombre
        FROM Articulos
        WHERE Activo = 1
        ORDER BY Nombre
    """)
    articulos = [fila[0] for fila in cursor.fetchall()]

    return render_template('nueva_partida.html', articulos=articulos)

 # -------------------------------
# INGRESO POR GUÍA
# -------------------------------
@app.route('/nueva_guia', methods=['GET', 'POST'])
def nueva_guia():

    if request.method == 'POST':
        datos = request.get_json()
        documento = (datos.get('documento') or '').strip()
        cliente = (datos.get('cliente') or '').strip()
        partidas = datos.get('partidas') or []
        es_crexsa = 'CREXSA' in cliente.upper()

        if not documento or not cliente or not partidas:
            return {'ok': False, 'error': 'Faltan datos de la guía.'}

        numeros = [p['numero'].strip() for p in partidas]
        if len(set(numeros)) != len(numeros):
            return {'ok': False, 'error': 'Hay números de partida repetidos en la guía.'}

        crudos = []
        if es_crexsa:
            crudos = [(p.get('codigo_crudo') or '').strip() for p in partidas]
            if '' in crudos:
                return {'ok': False, 'error': 'Falta el código de crudo en alguna partida.'}
            if len(set(crudos)) != len(crudos):
                return {'ok': False, 'error': 'Hay códigos de crudo repetidos en la guía.'}

        # Revisar que no existan ya en el sistema
        for n in numeros:
            cursor.execute("SELECT COUNT(*) FROM Partidas WHERE NumeroPartida = ?", (n,))
            if cursor.fetchone()[0] > 0:
                return {'ok': False, 'error': f'La partida {n} ya existe en el sistema.'}

        for c in crudos:
            cursor.execute("SELECT NumeroPartida FROM Partidas WHERE CodigoCrudo = ?", (c,))
            fila = cursor.fetchone()
            if fila:
                return {'ok': False, 'error': f'El código de crudo {c} ya está en la partida {fila[0]}.'}

        # Cargar todas juntas: si algo falla, no se guarda ninguna
        try:
            for p in partidas:
                numero = p['numero'].strip()
                codigo_crudo = p['codigo_crudo'].strip() if es_crexsa else None

                cursor.execute("""
                    INSERT INTO Partidas
                    (NumeroDocumento, NumeroPartida, Cliente, Color, CodColor,
                     Rollos, Kilos, ProcesoActual, Estado, Articulo, CodigoCrudo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Recepción', 'En proceso', ?, ?)
                """, (documento, numero, cliente, p['color'], p['codcolor'],
                      p['rollos'], p['kilos'], p['articulo'], codigo_crudo))

                cursor.execute("""
                    SELECT TOP 1 ProcesoID
                    FROM Procesos
                    WHERE NumeroPartida = ? AND NombreProceso = 'Recepción'
                    ORDER BY ProcesoID DESC
                """, (numero,))
                fila = cursor.fetchone()
                if fila is None:
                    raise ValueError(f'No se creó el proceso de Recepción de la partida {numero}.')

                cursor.execute("UPDATE Procesos SET Peso = ? WHERE ProcesoID = ?",
                               (p['peso'], fila[0]))

            conn.commit()

        except Exception as e:
            conn.rollback()
            return {'ok': False, 'error': f'No se pudo cargar la guía: {e}'}

        return {'ok': True}

    cursor.execute("SELECT Nombre FROM Articulos WHERE Activo = 1 ORDER BY Nombre")
    articulos = [f[0] for f in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT Cliente FROM Partidas WHERE Cliente IS NOT NULL ORDER BY Cliente")
    clientes = [f[0] for f in cursor.fetchall()]

    return render_template('nueva_guia.html', articulos=articulos, clientes=clientes)   

# -------------------------------
# EDITAR PARTIDA
# -------------------------------
@app.route('/editar_partida/<numero>', methods=['GET', 'POST'])
def editar_partida(numero):
    if request.method == 'POST':
        cliente = request.form['cliente']
        color = request.form['color']
        rollos = request.form['rollos']
        kilos = request.form['kilos']
        articulo = request.form['articulo']
        proceso = request.form['proceso']
        estado = request.form['estado']

        cursor.execute("""
            UPDATE Partidas 
            SET Cliente=?, Color=?, Rollos=?, Kilos=?, Articulo=?, ProcesoActual=?, Estado=? 
            WHERE NumeroPartida=?
        """, (cliente, color, rollos, kilos, articulo, proceso, estado, numero))
        conn.commit()
        return redirect('/')

    cursor.execute("""
        SELECT NumeroPartida, Cliente, Color, Rollos, Kilos, Articulo, ProcesoActual, Estado 
        FROM Partidas WHERE NumeroPartida=?
    """, (numero,))
    partida = cursor.fetchone()
    return render_template('editar_partida.html', partida=partida)

# -------------------------------
# ELIMINAR PARTIDA
# -------------------------------
@app.route('/eliminar_partida/<numero>')
def eliminar_partida(numero):
    cursor.execute("DELETE FROM Partidas WHERE NumeroPartida=?", (numero,))
    conn.commit()
    return redirect('/')

@app.route('/supervisor_tintoreria')
def supervisor_tintoreria():

    cursor.execute("""
            SELECT
        p.NumeroPartida,
        p.NumeroDocumento,
        p.Cliente,
        p.Color,
        p.Rollos,
        p.Kilos,
        p.ProcesoActual,
        p.Estado,
        p.Articulo,
        pr.NombreProceso,
        o.Nombre AS Operario,
        m.Nombre AS Maquina
    FROM Partidas p

    OUTER APPLY (
        SELECT TOP 1
            pr.NombreProceso,
            pr.OperarioID,
            pr.MaquinaID
        FROM Procesos pr
        WHERE pr.NumeroPartida = p.NumeroPartida
          AND pr.NombreProceso = 'Teñido'
        ORDER BY pr.ProcesoID DESC
    ) pr

    LEFT JOIN Operarios o
        ON pr.OperarioID = o.OperarioID

    LEFT JOIN Maquinas m
        ON pr.MaquinaID = m.MaquinaID
    """)

    partidas = cursor.fetchall()

    return render_template(
        'supervisor_tintoreria.html',
        partidas=partidas
    )

@app.route('/procesos')
def procesos():
    return render_template('procesos.html')
# -------------------------------
# CENTRO DE PROCESOS
# -------------------------------


# -------------------------------
# EJECUCIÓN DEL SERVIDOR
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
