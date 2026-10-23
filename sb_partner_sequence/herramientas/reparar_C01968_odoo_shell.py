"""Ejecutar DENTRO de `odoo shell -d BASE` (no como python normal).

Primero usar APLICAR = False. Revisar el resultado y solo entonces True.
No ejecutar mientras haya usuarios creando clientes. Tener copia de seguridad.
Este script REQUIERE transaccion explicita: al finalizar ejecutar env.cr.commit()
solo si APLICAR=True y todo termina sin excepciones.
"""
APLICAR = False
ID_CLIENTE_JULIAN = None  # OBLIGATORIO: copiar el ID numérico de la URL de Odoo

Partner = env['res.partner'].sudo().with_context(active_test=False)
Sequence = env['ir.sequence'].sudo()
seq = Sequence.search([('code', '=', 'res.partner.customer.sequence')], limit=1)
assert seq, 'No existe la secuencia de clientes'
assert seq.implementation == 'standard', 'Revisar manualmente: la implementación ya no es estándar'
assert seq.number_next_actual == 1970, 'La secuencia ya ha avanzado: detenerse y revisar'
assert ID_CLIENTE_JULIAN is not None, 'Introduce primero el ID de Julian Martin'
client = Partner.browse(ID_CLIENTE_JULIAN).exists()
assert len(client) == 1, 'Cliente no encontrado'
assert client.sequence_number == 'C01969', 'El cliente indicado no tiene el código esperado'
assert client.name.strip().lower() == 'julian martín'.lower(), 'El nombre no coincide: revisar tildes y el cliente'
for code in ('C01968', 'C01969'):
    users = Partner.search([('sequence_number', '=', code)])
    assert (not users) if code == 'C01968' else (len(users) == 1 and users.id == client.id), ('Conflicto con código %s: %s' % (code, users.ids))
print('VERIFICADO: cliente ID=%s, %s, actual=%s; secuencia siguiente=%s' % (client.id, client.name, client.sequence_number, seq.number_next_actual))
if not APLICAR:
    print('SIMULACION: se asignaria C01968 a Julian y siguiente numero C01969. Sin cambios.')
else:
    client.write({'sequence_number': 'C01968'})
    seq.write({'number_next_actual': 1969})
    assert client.sequence_number == 'C01968'
    assert seq.number_next_actual == 1969
    print('Cambios preparados. Si todo es correcto, ejecutar env.cr.commit(); si no, env.cr.rollback().')
