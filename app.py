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
    cursor.execute("SELECT NumeroPartida, Cliente, Color, Rollos, Kilos, ProcesoActual, Estado, Articulo FROM Partidas")
    partidas = cursor.fetchall()
    return render_template('index.html', partidas=partidas)

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
        articulo = request.form['articulo']
        proceso = request.form['proceso']
        estado = request.form['estado']

        cursor.execute("""
            INSERT INTO Partidas 
            (NumeroDocumento, NumeroPartida, Cliente, Color, CodColor, Rollos, Kilos, ProcesoActual, Estado, Articulo) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (documento, numero, cliente, color, codcolor, rollos, kilos, proceso, estado, articulo))
        conn.commit()
        return redirect('/')
    return render_template('nueva_partida.html')

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

# -------------------------------
# EJECUCIÓN DEL SERVIDOR
# -------------------------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
