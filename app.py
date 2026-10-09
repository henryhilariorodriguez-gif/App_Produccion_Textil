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


    # Si el supervisor confirma
    if request.method == 'POST':

        operario = request.form['operario']
        maquina = request.form['maquina']


        # Verificar que este proceso todavía no haya sido registrado
        if partida[3] != 'Pendiente de reproceso':

            cursor.execute("""
                SELECT COUNT(*)
                FROM Procesos
                WHERE NumeroPartida = ?
                  AND NombreProceso = ?
                  AND TipoProceso = ?
            """, (numero, siguiente_proceso, 'Normal'))

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

            cursor.execute("""
                UPDATE Partidas
                SET ProcesoActual = ?
                WHERE NumeroPartida = ?
            """, (siguiente_proceso, numero))


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
        maquinas=maquinas
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
          AND pr.NombreProceso = 'Tintoreria'
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
