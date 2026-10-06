# App Producción Textil

Aplicación web para seguir partidas de producción textil por sus procesos
(recepción, tintorería, secado, etc.).

## Tecnologías
- Python + Flask
- SQL Server (base ProduccionTextil) con pyodbc
- HTML, CSS y JavaScript

## Cómo arrancar
1. Instalar dependencias: `pip install -r requirements.txt`
2. Tener SQL Server Express activo con la base ProduccionTextil.
3. Ejecutar: `python app.py`
4. Abrir http://localhost:5000

## Pantallas principales
- `/` lista de partidas
- `/nueva_partida` registrar partida
- `/procesos` panel de áreas
- `/supervisor_tintoreria` control de tintorería
