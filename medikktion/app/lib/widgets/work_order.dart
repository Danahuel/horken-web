import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import 'instruments.dart';

/// Hoja para cerrar una avería con lo que costó de verdad. Esos costes reales
/// sustituyen a la estimación en las próximas lecturas.
Future<void> showWorkOrderSheet(BuildContext context, SessionRepository repo, Session s, Map<String, dynamic> d) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: context.p.surface,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(18))),
    builder: (_) => _WorkOrderForm(repo: repo, s: s, d: d),
  );
}

class _WorkOrderForm extends StatefulWidget {
  final SessionRepository repo;
  final Session s;
  final Map<String, dynamic> d;
  const _WorkOrderForm({required this.repo, required this.s, required this.d});
  @override
  State<_WorkOrderForm> createState() => _WorkOrderFormState();
}

class _WorkOrderFormState extends State<_WorkOrderForm> {
  final _cost = TextEditingController();
  final _hours = TextEditingController();
  final _parts = TextEditingController();
  final _notes = TextEditingController();
  bool _busy = false;
  String? _error;

  double? _num(String t) => double.tryParse(t.trim().replaceAll('.', '').replaceAll(',', '.'));

  Future<void> _save() async {
    final cost = _num(_cost.text);
    if (cost == null || cost <= 0) {
      setState(() => _error = 'Indique el coste total real (piezas + mano de obra).');
      return;
    }
    setState(() => _busy = true);
    String? who;
    try {
      who = FirebaseAuth.instance.currentUser?.email;
    } catch (_) {}
    await widget.repo.addWorkOrder(widget.s.id, {
      'code': widget.d['code'], 'name': widget.d['name'], 'cost_eur': cost,
      'labour_hours': _num(_hours.text), 'parts': _parts.text.trim(), 'notes': _notes.text.trim(),
      'estimate_min': widget.d['cost_min_eur'], 'estimate_max': widget.d['cost_max_eur'],
      'machine': widget.s.title, 'serial': widget.s.machine['serial'], 'by': who ?? 'demostración',
      'at': DateTime.now().toUtc().toIso8601String(),
    });
    if (!mounted) return;
    Navigator.pop(context);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Reparación registrada. Se usará para afinar los próximos presupuestos.')));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Padding(
      padding: EdgeInsets.fromLTRB(22, 18, 22, MediaQuery.of(context).viewInsets.bottom + 22),
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          Center(child: Container(width: 36, height: 3, decoration: BoxDecoration(color: p.line2, borderRadius: BorderRadius.circular(2)))),
          const SizedBox(height: 18),
          Text('REGISTRAR REPARACIÓN', style: label(context, color: p.gold)),
          const SizedBox(height: 8),
          Text('${widget.d['name']}', style: tx(context, 18, w: FontWeight.w400)),
          Text('${widget.d['code']} · estimado ${euros(widget.d['cost_min_eur'], widget.d['cost_max_eur'])}',
              style: tx(context, 12.5, color: p.text3)),
          const SizedBox(height: 18),
          Row(children: [
            Expanded(child: _field('COSTE TOTAL REAL (€)', _cost, number: true)),
            const SizedBox(width: 12),
            Expanded(child: _field('HORAS DE MANO DE OBRA', _hours, number: true)),
          ]),
          _field('PIEZAS CAMBIADAS', _parts),
          _field('NOTAS', _notes, lines: 3),
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 6),
              child: Text(_error!, style: tx(context, 12.5, color: p.danger))),
          const SizedBox(height: 16),
          GoldButton('Guardar reparación', onTap: _save, busy: _busy),
        ]),
      ),
    );
  }

  Widget _field(String l, TextEditingController c, {bool number = false, int lines = 1}) => Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(l, style: label(context, size: 9)),
          const SizedBox(height: 6),
          TextField(controller: c, minLines: lines, maxLines: lines, style: tx(context, 14),
              keyboardType: number ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text),
        ]),
      );
}
