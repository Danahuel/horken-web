import 'package:flutter/material.dart';

import '../data/session.dart';
import '../theme.dart';
import 'instruments.dart';

/// Resultado (o progreso) de la prueba de bombas que se hace desde el portátil.
class PumpTestPanel extends StatelessWidget {
  final Session s;
  const PumpTestPanel({super.key, required this.s});

  static const _st = {'ok': 'Bien', 'justa': 'Justa', 'baja': 'Baja', 'alta': 'Alta'};
  static const _src = {'centralita': 'centralita', 'manometro': 'manómetro'};

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final t = s.pumpTest;
    final res = (t['result'] as Map?)?.cast<String, dynamic>() ?? {};
    final checks = ((res['checks'] as List?) ?? []).cast<Map>();
    final faults = ((res['faults'] as List?) ?? []).cast<Map>();
    final steps = ((t['steps'] as List?) ?? []).cast<Map>();
    final active = t['active'] == true;
    final idx = (t['index'] as num?)?.toInt() ?? 0;
    final vc = switch (res['verdict']) { 'ok' => p.ok, 'justa' => p.warn, 'mal' => p.danger, _ => p.text3 };
    Color sc(String? st) => switch (st) { 'ok' => p.ok, 'justa' => p.warn, 'baja' || 'alta' => p.danger, _ => p.text3 };

    return Panel(
      border: res['verdict'] == 'mal' && !active ? p.danger.withValues(alpha: 0.45) : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (active && steps.isNotEmpty) ...[
          const LivePulse(text: 'PRUEBA EN CURSO EN EL PORTÁTIL'),
          const SizedBox(height: 10),
          Text('Paso ${idx + 1} de ${steps.length} · ${steps[idx]['title']}', style: tx(context, 15.5, w: FontWeight.w500)),
          const SizedBox(height: 4),
          Text('${steps[idx]['instruction']}', style: tx(context, 12.5, color: p.text2, h: 1.5)),
          const SizedBox(height: 14),
        ] else ...[
          Text('${res['label'] ?? 'Prueba sin lecturas'}', style: tx(context, 16.5, w: FontWeight.w500, color: vc)),
          const SizedBox(height: 4),
          Text(t['spec_source'] == 'manual' ? 'Referencias del manual de la máquina' : 'Referencias orientativas',
              style: tx(context, 11.5, color: p.text3)),
          const SizedBox(height: 14),
        ],
        for (final c in checks) ...[
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${c['label']}'.toUpperCase(), style: label(context, size: 9)),
              const SizedBox(height: 3),
              Text('${c['title']}', style: tx(context, 12.5, color: p.text2)),
            ])),
            Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Text.rich(TextSpan(children: [
                TextSpan(text: fmtNum(c['value'], decimals: c['channel'] == 'pilot_bar' ? 1 : 0), style: num_(context, 21)),
                TextSpan(text: ' bar', style: tx(context, 11, color: p.text3)),
              ])),
              Text(_ref(c), style: mono(context, 10.5, color: p.text3)),
            ]),
            const SizedBox(width: 12),
            SizedBox(width: 52, child: Text(_st[c['status']] ?? '—', textAlign: TextAlign.right,
                style: tx(context, 12.5, w: FontWeight.w600, color: sc(c['status'] as String?)))),
          ]),
          const SizedBox(height: 6),
          _bar(context, c, sc(c['status'] as String?)),
          Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 12),
            child: Text('Fuente: ${_src[c['source']] ?? c['source']}', style: tx(context, 10.5, color: p.text3)),
          ),
        ],
        if (res['comparison'] is Map)
          Text('${(res['comparison'] as Map)['text']}', style: tx(context, 12.5, color: p.text2, h: 1.45)),
        if (faults.isNotEmpty) ...[
          Divider(color: p.line, height: 26),
          for (final f in faults) ...[
            Text('${f['name']}', style: tx(context, 14, w: FontWeight.w500, color: p.danger)),
            const SizedBox(height: 4),
            Text('Reparación: ${euros(f['cost_min_eur'], f['cost_max_eur'])} · dificultad ${f['difficulty']}/5',
                style: tx(context, 12.5, color: p.gold)),
            const SizedBox(height: 4),
            Text('Primero: ${((f['steps'] as List?) ?? []).take(1).join()}',
                style: tx(context, 12, color: p.text2, h: 1.45)),
            const SizedBox(height: 10),
          ],
          Text('Detalle completo en Averías.', style: tx(context, 11.5, color: p.text3)),
        ],
        const SizedBox(height: 10),
        Text('${res['note'] ?? ''}', style: tx(context, 11, color: p.text3, h: 1.5)),
      ]),
    );
  }

  String _ref(Map c) {
    final r = c['range'] as List?;
    final ref = r != null ? 'ref. ${r[0]}-${r[1]}' : 'ref. ${fmtNum(c['nominal'], decimals: 0)}';
    final d = asNum(c['deviation_pct']);
    return d == null ? ref : '$ref · ${d > 0 ? '+' : ''}${fmtNum(d, decimals: 0)} %';
  }

  /// Barra: dónde cae la lectura respecto a la referencia (la marca es el valor del manual).
  Widget _bar(BuildContext context, Map c, Color color) {
    final p = context.p;
    final v = (asNum(c['value']) ?? 0).toDouble();
    final r = c['range'] as List?;
    final ref = r != null ? (asNum(r[1]) ?? 1).toDouble() : (asNum(c['nominal']) ?? 1).toDouble();
    final max = ref * 1.25;
    return LayoutBuilder(builder: (context, box) {
      final w = box.maxWidth;
      return SizedBox(height: 8, child: Stack(children: [
        Positioned(left: 0, right: 0, top: 3, child: Container(height: 2, color: p.line)),
        Positioned(left: 0, top: 3, child: Container(height: 2, width: w * (v / max).clamp(0, 1), color: color)),
        Positioned(left: w * (ref / max) - 0.5, top: 0, child: Container(width: 1, height: 8, color: p.text3)),
      ]));
    });
  }
}
