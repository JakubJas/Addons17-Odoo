MODULO UNIFICADO PARA ODOO 17
=============================

Este ZIP contiene el modulo sb_partner_sequence y una herramienta manual
para revisar/recuperar el salto C01968-C01969.

1) ACTUALIZACION DEL MODULO
- Hacer copia de seguridad y probar primero en Odoo de demostracion.
- Sustituir la carpeta sb_partner_sequence del addons path con esta carpeta.
- Reiniciar Odoo y actualizar el modulo desde Aplicaciones.
- La actualizacion NO modifica por si sola el codigo C01969 de Julian,
  ni recupera C01968, ni cambia la implementacion de la secuencia.

2) REPARACION PUNTUAL (SOLO UNA VEZ Y SUPERVISADA)
- Leer herramientas/INSTRUCCIONES_REPARACION.txt.
- Ejecutar el archivo herramientas/reparar_C01968_odoo_shell.py dentro de
  una sesion odoo shell, primero APLICAR=False (simulacion).
- Introducir el ID REAL del registro Julian Martin.
- Detener temporalmente nuevas altas de clientes durante la reparacion.
- Verificar que nadie usa C01968, que Julian tiene C01969 y que el
  siguiente numero continua en 1970. Ante cualquier discrepancia, parar.
- La reparacion requiere operador con acceso al servidor y una copia
  de seguridad valida. NO se ejecuta al instalar o actualizar.

3) NUMERACION FUTURA
- Si se desea evitar consumo por transacciones fallidas, estudiar cambiar
  la implementacion de la secuencia a 'Sin huecos' (no_gap) tras probar
  compatibilidad y concurrencia en un entorno de pruebas.
- No garantiza ausencia de huecos por borrados, alteraciones manuales ni
  operaciones que si llegan a confirmarse.

IMPORTANTE: No revertir el contador sin verificar antes todos los
contactos (tambien archivados) y otros procesos que compartan la secuencia.
