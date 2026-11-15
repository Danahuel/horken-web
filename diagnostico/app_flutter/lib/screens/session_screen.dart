import 'dart:async';

import 'package:flutter/material.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import '../widgets/common.dart';

class SessionScreen extends StatefulWidget {
  final SessionRepository repo;
  final String id;
  const SessionScreen({super.key, required this.repo, required this.id});
  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> {
  int _tab = 0;
  Session? _s;
  final Map<String, List<double>> _history = {};
  StreamSubscription? _sub;

  @override
  void initState() {
    super.initState();
    _sub = widget.repo.session(widget.id).listen((s) {
      if (s == null) return;
      s.live.forEach((k, v) {
        final n = asNum((v as Map)['value']);
        if (n == null) return;
        final h = _history.putIfAbsent(k, () => []);
        h.add(n.toDouble());
        if (h.length > 90) h.removeAt(0);
      });
      setState(() => _s = s);
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = _s;
    final k = context.ink;
    if (s == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final active = s.dtcs.where((d) => d['active'] == true).length;
    final pages = [
      SummaryTab(s: s, goTo: (i) => setState(() => _tab = i)),
      DtcsTab(s: s),
      EcusTab(s: s),
      LiveTab(s: s, history: _history),
      ReportTab(s: s, repo: widget.repo),
    ];
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(s.title.toUpperCase(), style: cond(context, 21, w: FontWeight.w700, ls: 0.4)),
          Text('parte ${s.shortId}', style: mono(context, 11, color: k.ink3)),
        ]),
        actions: [if (s.isLive) const Padding(padding: EdgeInsets.only(right: 16), child: LiveMark())],
        bottom: const PreferredSize(preferredSize: Size.fromHeight(2), child: Rule(strong: true)),
      ),
      body: pages[_tab],
      bottomNavigationBar: _TabBar(
        index: _tab,
        onTap: (i) => setState(() => _tab = i),
        items: [('Resumen', null), ('Averías', active), ('Centralitas', null), ('En vivo', null), ('Enviar', null)],
      ),
    );
  }
}

/// Pestañas de texto, sin iconos: la activa lleva una barra encima.
class _TabBar extends StatelessWidget {
  final int index;
  final ValueChanged<int> onTap;
  final List<(String, int?)> items;
  const _TabBar({required this.index, required this.onTap, required this.items});
  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return Container(
      decoration: BoxDecoration(color: k.paper, border: Border(top: BorderSide(color: k.ink, width: 2))),
      child: SafeArea(
        top: false,
        child: Row(children: [
          for (var i = 0; i < items.length; i++)
            Expanded(
              child: InkWell(
                onTap: () => onTap(i),
                child: Container(
                  height: 54,
                  decoration: BoxDecoration(border: Border(top: BorderSide(
                      color: i == index ? k.accent : Colors.transparent, width: 4))),
                  alignment: Alignment.center,
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Flexible(
                      child: Text(items[i].$1.toUpperCase(), overflow: TextOverflow.fade, softWrap: false,
                          style: cond(context, 13.5, w: i == index ? FontWeight.w700 : FontWeight.w500,
                              color: i == index ? k.ink : k.ink2, ls: 0.6)),
                    ),
                    if ((items[i].$2 ?? 0) > 0) ...[
                      const SizedBox(width: 4),
                      Text('${items[i].$2}', style: mono(context, 11, w: FontWeight.w600, color: k.accent)),
                    ],
                  ]),
                ),
              ),
            ),
        ]),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════ RESUMEN
class SummaryTab extends StatelessWidget {
  final Session s;
  final void Function(int) goTo;
  const SummaryTab({super.key, required this.s, required this.goTo});

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final sum = s.summary, t = s.tamper, m = s.machine, l = s.lamps;
    final verdict = t['verdict'] as String?;
    final vc = k.verdict(verdict);
    final urgent = s.dtcs.where((d) => d['active'] == true && (d['severity'] as num) >= 4).toList();
    final mods = ((s.modifications['findings'] as List?) ?? []).cast<Map>();
    final evidence = ((t['evidence'] as List?) ?? []).cast<Map>();
    var n = 0;
    String next() => (++n).toString().padLeft(2, '0');

    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      // Cabecera tipo ficha
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
        child: Text('${m['machine_class_label'] ?? ''} · nº serie ${m['serial'] ?? '—'}'
            '${s.location.isNotEmpty ? ' · ${s.location}' : ''}',
            style: body(context, 14, color: k.ink2)),
      ),
      // Testigos
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 14),
        child: Wrap(spacing: 18, runSpacing: 6, children: [
          _lamp(context, 'Parada', l['red_stop'] == true, k.danger),
          _lamp(context, 'Aviso', l['amber_warning'] == true, k.warn),
          _lamp(context, 'Emisiones', l['mil'] == true, k.warn),
          _lamp(context, 'Protección', l['protect'] == true, k.warn),
        ]),
      ),
      const Rule(),
      // Cifras
      IntrinsicHeight(
        child: Row(children: [
          _figure(context, '${sum['active_dtcs'] ?? 0}', 'activas', k.severity(s.maxSeverity), () => goTo(1)),
          VerticalDivider(width: 1, color: k.rule),
          _figure(context, '${sum['history_dtcs'] ?? 0}', 'históricas', null, () => goTo(1)),
          VerticalDivider(width: 1, color: k.rule),
          _figure(context, '${sum['ecus'] ?? 0}', 'centralitas', null, () => goTo(2)),
        ]),
      ),
      const Rule(),
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
        child: Row(children: [
          Text('Reparar lo activo: ', style: body(context, 14, color: k.ink2)),
          Text(euros(sum['repair_cost_min_eur'], sum['repair_cost_max_eur']),
              style: mono(context, 14, w: FontWeight.w600)),
        ]),
      ),

      // Horas y km
      SectionHeader(next(), 'Horas y kilómetros'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.only(left: 4, bottom: 14, top: 4),
            child: VerdictStamp(switch (verdict) {
              'manipulado' => 'Manipuladas',
              'sospechoso' => 'Revisar',
              'ok' => 'Correctas',
              _ => 'Sin datos',
            }, vc),
          ),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Expanded(child: _reading(context, 'marca', t['reported_hours'], k.ink)),
            if (t['estimated_real_hours'] != null)
              Expanded(child: _reading(context, 'real, aprox.', t['estimated_real_hours'], vc, approx: true)),
          ]),
          const SizedBox(height: 10),
          Text('${t['checks'] ?? 0} comprobaciones cruzadas · sospecha ${t['score'] ?? 0}/100',
              style: mono(context, 11, color: k.ink3)),
          const SizedBox(height: 14),
          for (final e in evidence) _evidence(context, e),
        ]),
      ),

      if (mods.isNotEmpty) ...[
        SectionHeader(next(), 'Centralitas modificadas'),
        Padding(padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(children: [for (final f in mods) _evidence(context, f)])),
      ],

      if (urgent.isNotEmpty) ...[
        SectionHeader(next(), 'Lo primero que miraría'),
        for (final d in urgent)
          InkWell(
            onTap: () => goTo(1),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 8),
              child: Row(children: [
                SevStamp((d['severity'] as num).toInt(), size: 28),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${d['name']}', style: body(context, 15, w: FontWeight.w600)),
                  Text(d['warning'] != null ? '${d['warning']}' : '${d['fmi_text']}',
                      style: body(context, 13, color: d['warning'] != null ? k.danger : k.ink2)),
                ])),
                Icon(Icons.chevron_right, color: k.ink3),
              ]),
            ),
          ),
      ],

      SectionHeader(next(), 'Ficha de la máquina'),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(children: [
          KV('Marca', '${m['brand_name'] ?? ''}'),
          KV('Modelo', '${m['model'] ?? ''}'),
          KV('Nº de serie', '${m['serial'] ?? ''}', monoValue: true),
          if ('${m['vin'] ?? ''}'.isNotEmpty) KV('VIN', '${m['vin']}', monoValue: true),
          KV('Conector', '${m['connector'] ?? ''}'),
          KV('Software oficial', '${m['official_software'] ?? ''}'),
          KV('Leído por', s.protocols.join(' · ')),
          if (s.operator.isNotEmpty) KV('Operador', s.operator),
          const SizedBox(height: 8),
          Text('${m['brand_note'] ?? ''}', style: body(context, 13, color: k.ink2)),
        ]),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
        child: Text('${fmtNum(sum['frames'], decimals: 0)} tramas leídas${s.simulated ? ' · máquina simulada' : ''}',
            style: mono(context, 11, color: k.ink3)),
      ),
    ]);
  }

  Widget _lamp(BuildContext c, String label, bool on, Color color) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 11, height: 11, decoration: BoxDecoration(
            color: on ? color : Colors.transparent, border: Border.all(color: on ? color : c.ink.ink3, width: 1.4))),
        const SizedBox(width: 6),
        Text(label, style: body(c, 14, w: on ? FontWeight.w600 : FontWeight.w400, color: on ? c.ink.ink : c.ink.ink3)),
      ]);

  Widget _figure(BuildContext c, String v, String label, Color? color, VoidCallback onTap) => Expanded(
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: Column(children: [
              Text(v, style: cond(c, 38, w: FontWeight.w700, color: color)),
              Text(label, style: body(c, 13, color: c.ink.ink2)),
            ]),
          ),
        ),
      );

  Widget _reading(BuildContext c, String label, dynamic h, Color color, {bool approx = false}) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: body(c, 13, color: c.ink.ink3)),
        Text('${approx ? '≈ ' : ''}${fmtNum(h, decimals: approx ? 0 : 1)} h',
            style: mono(c, 22, w: FontWeight.w600, color: color)),
      ]);

  Widget _evidence(BuildContext c, Map e) {
    final k = c.ink;
    final ok = e['level'] == 'ok';
    final color = ok ? k.ok : (e['level'] == 'alta' ? k.danger : k.warn);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(width: 3, height: 18, margin: const EdgeInsets.only(top: 2, right: 12), color: color),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${e['title']}', style: body(c, 15, w: FontWeight.w600)),
          const SizedBox(height: 2),
          Text('${e['detail']}', style: body(c, 13.5, color: k.ink2)),
        ])),
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════ AVERÍAS
class DtcsTab extends StatefulWidget {
  final Session s;
  const DtcsTab({super.key, required this.s});
  @override
  State<DtcsTab> createState() => _DtcsTabState();
}

class _DtcsTabState extends State<DtcsTab> {
  int _filter = 0;  // 0 activas, 1 históricas, 2 todas
  final Set<String> _open = {};

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final all = widget.s.dtcs;
    final act = all.where((d) => d['active'] == true).toList();
    final his = all.where((d) => d['active'] != true).toList();
    final list = [act, his, all][_filter];
    if (_open.isEmpty && list.isNotEmpty && _filter == 0) _open.add(_key(list.first));
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
        child: Row(children: [
          _filterBtn(context, 'Activas', act.length, 0),
          _filterBtn(context, 'Históricas', his.length, 1),
          _filterBtn(context, 'Todas', all.length, 2),
        ]),
      ),
      const Rule(),
      if (list.isEmpty)
        Padding(padding: const EdgeInsets.all(28),
            child: Text(_filter == 0 ? 'Ninguna avería activa ahora mismo.' : 'Nada en esta lista.',
                style: body(context, 15, color: k.ink2))),
      for (final d in list) ...[
        _DtcRow(d: d, open: _open.contains(_key(d)), onTap: () => setState(() {
          final key = _key(d);
          _open.contains(key) ? _open.remove(key) : _open.add(key);
        })),
        const Rule(),
      ],
    ]);
  }

  String _key(Map d) => '${d['source']}|${d['code']}';

  Widget _filterBtn(BuildContext c, String t, int n, int i) {
    final k = c.ink;
    final sel = _filter == i;
    return InkWell(
      onTap: () => setState(() => _filter = i),
      child: Container(
        padding: const EdgeInsets.fromLTRB(8, 8, 12, 10),
        decoration: BoxDecoration(border: Border(bottom: BorderSide(color: sel ? k.accent : Colors.transparent, width: 3))),
        child: Text.rich(TextSpan(children: [
          TextSpan(text: t.toUpperCase(), style: cond(c, 15, w: sel ? FontWeight.w700 : FontWeight.w500,
              color: sel ? k.ink : k.ink2, ls: 0.6)),
          TextSpan(text: ' $n', style: mono(c, 12, color: sel ? k.accent : k.ink3)),
        ])),
      ),
    );
  }
}

class _DtcRow extends StatelessWidget {
  final Map<String, dynamic> d;
  final bool open;
  final VoidCallback onTap;
  const _DtcRow({required this.d, required this.open, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final sev = (d['severity'] as num).toInt();
    final parts = ((d['parts'] as List?) ?? []).cast<Map>();
    final causes = ((d['causes'] as List?) ?? []).cast<String>();
    final steps = ((d['steps'] as List?) ?? []).cast<String>();
    final occ = (d['occurrences'] as num?)?.toInt() ?? 0;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 16, 14),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SevStamp(sev),
            const SizedBox(width: 14),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${d['code']}${d['protocol'] != null && d['protocol'] != 'J1939' ? '  ·  ${d['protocol']}' : ''}',
                  style: mono(context, 11.5, color: k.ink3)),
              const SizedBox(height: 2),
              Text('${d['name']}', style: cond(context, 19, w: FontWeight.w700)),
              Text('${d['fmi_text']}', style: body(context, 14, color: k.ink2)),
              const SizedBox(height: 6),
              Text([
                '${d['source_name']}',
                if (occ > 0) '$occ ${occ == 1 ? 'vez' : 'veces'}',
                if (d['active'] != true) 'ya no está activa',
              ].join('  ·  '), style: body(context, 12.5, color: k.ink3)),
            ])),
            Padding(padding: const EdgeInsets.only(top: 18),
                child: Icon(open ? Icons.expand_less : Icons.expand_more, color: k.ink3)),
          ]),
        ),
      ),
      AnimatedSize(
        duration: const Duration(milliseconds: 180),
        alignment: Alignment.topCenter,
        child: !open ? const SizedBox(width: double.infinity) : Padding(
          padding: const EdgeInsets.fromLTRB(68, 0, 20, 20),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (d['warning'] != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                decoration: BoxDecoration(color: k.danger.withValues(alpha: 0.09),
                    border: Border(left: BorderSide(color: k.danger, width: 4))),
                child: Text('${d['warning']}', style: body(context, 14.5, w: FontWeight.w600, color: k.danger)),
              ),
            if (causes.isNotEmpty) ...[
              _h(context, 'Por qué suele pasar'),
              for (final x in causes) Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('–  ', style: body(context, 14, color: k.ink3)),
                  Expanded(child: Text(x, style: body(context, 14))),
                ]),
              ),
              const SizedBox(height: 10),
            ],
            _h(context, 'Qué hacer, en este orden'),
            for (var i = 0; i < steps.length; i++) Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 28, child: Text((i + 1).toString().padLeft(2, '0'),
                    style: mono(context, 13, w: FontWeight.w600, color: k.accent))),
                Expanded(child: Text(steps[i], style: body(context, 14))),
              ]),
            ),
            const SizedBox(height: 10),
            _h(context, 'Piezas y precio orientativo'),
            if (parts.isEmpty) Text('No hace falta pieza: diagnóstico o ajuste.', style: body(context, 14, color: k.ink2)),
            for (final p in parts) Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Expanded(child: Text('${p['nombre']}', style: body(context, 14))),
                const SizedBox(width: 10),
                Text(euros(p['min'], p['max']), style: mono(context, 13, w: FontWeight.w600)),
              ]),
            ),
            Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Rule()),
            Row(children: [
              Expanded(child: Text('Mano de obra ${fmtNum(d['labour_hours'])} h', style: body(context, 14, color: k.ink2))),
              Text(euros(d['cost_min_eur'], d['cost_max_eur']), style: mono(context, 14, w: FontWeight.w600, color: k.accent)),
            ]),
            const SizedBox(height: 14),
            _h(context, 'Dificultad'),
            DifficultyBars((d['difficulty'] as num).toInt()),
            const SizedBox(height: 14),
            if (d['name_language'] == 'en')
              Text('Descripción oficial SAE (en inglés).', style: body(context, 12, color: k.ink3)),
            if (d['known'] != true)
              Text(d['proprietary'] == true
                  ? 'Código propio del fabricante: su significado exacto está en el software oficial de la marca.'
                  : 'Este código aún no está en la base de Horken.',
                  style: body(context, 12.5, color: k.warn)),
            Text('Precios orientativos, de recambio alternativo a original. Confirmar referencia por nº de serie.',
                style: body(context, 12, color: k.ink3)),
          ]),
        ),
      ),
    ]);
  }

  Widget _h(BuildContext c, String t) => Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(t.toUpperCase(), style: cond(c, 13, w: FontWeight.w700, color: c.ink.ink2, ls: 1.2)));
}

// ═══════════════════════════════════════════════════════════════ CENTRALITAS
class EcusTab extends StatelessWidget {
  final Session s;
  const EcusTab({super.key, required this.s});

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
        child: Text('${s.ecus.length} centralitas han contestado. Si alguna que debería estar no aparece, '
            'revisa su alimentación o el cableado CAN.', style: body(context, 14, color: k.ink2)),
      ),
      const Rule(),
      for (final e in s.ecus) ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              SizedBox(width: 92, child: Text('${e['address_hex']}', style: mono(context, 12, w: FontWeight.w600, color: k.accent))),
              Expanded(child: Text('${e['name']}', style: cond(context, 18, w: FontWeight.w700))),
              Text('${e['protocol'] ?? ''}', style: mono(context, 11, color: k.ink3)),
            ]),
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.only(left: 92),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text([
                  (e['active_dtcs'] as num) == 0 ? 'sin averías activas' : '${e['active_dtcs']} activas',
                  if ((e['history_dtcs'] as num) > 0) '${e['history_dtcs']} históricas',
                  if (e['engine_hours'] != null) '${fmtNum(e['engine_hours'])} h',
                ].join('  ·  '), style: body(context, 14, w: FontWeight.w500,
                    color: (e['active_dtcs'] as num) > 0 ? k.accent : k.ink)),
                const SizedBox(height: 4),
                for (final sw in ((e['software'] as List?) ?? []))
                  Text('$sw', style: mono(context, 11.5, color: k.ink2)),
                for (final c in ((e['calibrations'] as List?) ?? []).cast<Map>())
                  Text('cal ${c['cal_id']} · cvn ${c['cvn']}', style: mono(context, 11.5, color: k.ink2)),
                if (e['ecu_id'] is Map && '${(e['ecu_id'] as Map)['part_number'] ?? ''}'.isNotEmpty)
                  Text('ref. ${(e['ecu_id'] as Map)['part_number']}', style: mono(context, 11.5, color: k.ink2)),
                if (e['total_revolutions'] != null)
                  Text('${fmtNum(e['total_revolutions'], decimals: 0)} rev. totales', style: mono(context, 11.5, color: k.ink2)),
                if (e['total_fuel_l'] != null)
                  Text('${fmtNum(e['total_fuel_l'], decimals: 0)} L de gasoil en su vida', style: mono(context, 11.5, color: k.ink2)),
                if (e['total_km'] != null)
                  Text('${fmtNum(e['total_km'], decimals: 0)} km', style: mono(context, 11.5, color: k.ink2)),
              ]),
            ),
          ]),
        ),
        const Rule(),
      ],
    ]);
  }
}

// ═══════════════════════════════════════════════════════════════ EN VIVO
// [mín escala, máx escala, normal desde, normal hasta]
const _scale = <String, List<double?>>{
  'rpm': [0, 2500, 700, 2100],
  'oil_pressure_kpa': [0, 700, 200, 600],
  'coolant_c': [20, 120, 70, 100],
  'hyd_oil_temp_c': [10, 110, 30, 85],
  'trans_oil_temp_c': [10, 130, 40, 100],
  'oil_temp_c': [10, 130, 60, 110],
  'boost_kpa': [0, 300, null, null],
  'battery_v': [18, 32, 24.5, 29.5],
  'fuel_rate_lh': [0, 60, null, null],
  'torque_pct': [0, 100, null, null],
  'intake_temp_c': [0, 90, 10, 65],
  'fuel_level_pct': [0, 100, 15, 100],
  'def_level_pct': [0, 100, 15, 100],
  'oil_level_pct': [0, 100, 60, 100],
  'coolant_level_pct': [0, 100, 60, 100],
  'fuel_temp_c': [0, 90, null, 70],
  'ambient_c': [-20, 50, null, null],
  'speed_kmh': [0, 120, null, null],
  'load_pct': [0, 100, null, null],
};

const _order = ['rpm', 'oil_pressure_kpa', 'coolant_c', 'hyd_oil_temp_c', 'boost_kpa', 'fuel_rate_lh', 'torque_pct',
  'battery_v', 'oil_temp_c', 'trans_oil_temp_c', 'intake_temp_c', 'fuel_level_pct', 'def_level_pct', 'oil_level_pct',
  'coolant_level_pct', 'fuel_temp_c', 'ambient_c'];

class LiveTab extends StatelessWidget {
  final Session s;
  final Map<String, List<double>> history;
  const LiveTab({super.key, required this.s, required this.history});

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final live = s.live;
    final keys = [..._order.where(live.containsKey), ...live.keys.where((x) => !_order.contains(x))];
    final u = s.updatedAt;
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 12),
        child: Row(children: [
          if (s.isLive) LiveMark(suffix: u == null ? '' : ' · ${hhmm(u)}:${u.second.toString().padLeft(2, '0')}')
          else Text('Últimos valores leídos ${whenText(u)}', style: mono(context, 11, color: k.ink3)),
        ]),
      ),
      const Rule(),
      for (final key in keys) ...[
        _row(context, key, (live[key] as Map).cast<String, dynamic>()),
        const Rule(indent: 20),
      ],
    ]);
  }

  Widget _row(BuildContext c, String key, Map<String, dynamic> p) {
    final k = c.ink;
    final v = asNum(p['value'])?.toDouble() ?? 0;
    final sc = _scale[key];
    var color = k.ink;
    String? note;
    if (sc != null && sc[2] != null && v < sc[2]!) {
      color = k.danger;
      note = 'bajo';
    } else if (sc != null && sc[3] != null && v > sc[3]!) {
      color = k.danger;
      note = 'alto';
    }
    final lo = sc?[0] ?? 0, hi = sc?[1] ?? (v.abs() * 1.5 + 1);
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
      child: Column(children: [
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${p['label']}', style: body(c, 14.5, w: FontWeight.w500)),
            if (note != null) Text(note.toUpperCase(), style: cond(c, 12, w: FontWeight.w700, color: color, ls: 1)),
          ])),
          SizedBox(width: 60, height: 22, child: Trend(history[key] ?? const [], note != null ? color : k.ink3)),
          const SizedBox(width: 14),
          SizedBox(
            width: 108,
            child: Text.rich(TextSpan(children: [
              TextSpan(text: fmtNum(v, decimals: v.abs() >= 100 ? 0 : 1), style: mono(c, 22, w: FontWeight.w600, color: color)),
              TextSpan(text: ' ${p['unit']}', style: mono(c, 11, color: k.ink3)),
            ]), textAlign: TextAlign.right),
          ),
        ]),
        if (sc != null) ...[
          const SizedBox(height: 8),
          RangeBar(value: v, min: lo, max: hi, lo: sc[2], hi: sc[3], color: note != null ? color : k.accent),
        ],
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════ ENVIAR
class ReportTab extends StatefulWidget {
  final Session s;
  final SessionRepository repo;
  const ReportTab({super.key, required this.s, required this.repo});
  @override
  State<ReportTab> createState() => _ReportTabState();
}

class _ReportTabState extends State<ReportTab> {
  late List<String> _to = [...widget.s.recipients];
  final _ctrl = TextEditingController();
  bool _sending = false;

  void _add() {
    final e = _ctrl.text.trim();
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(e)) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Ese email no parece correcto')));
      return;
    }
    setState(() {
      if (!_to.contains(e)) _to = [..._to, e];
      _ctrl.clear();
    });
    widget.repo.saveRecipients(widget.s.id, _to);
  }

  Future<void> _send() async {
    setState(() => _sending = true);
    await widget.repo.requestReport(widget.s.id, _to);
    if (!mounted) return;
    setState(() => _sending = false);
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pedido. El portátil prepara el PDF y lo manda en unos segundos.')));
  }

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final st = widget.s.reportStatus;
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 4),
        child: Text('El parte completo en PDF: horas, averías con su solución, piezas, precios y centralitas.',
            style: body(context, 14, color: k.ink2)),
      ),
      SectionHeader('01', 'Para quién'),
      const Rule(),
      if (_to.isEmpty)
        Padding(padding: const EdgeInsets.fromLTRB(20, 14, 20, 14),
            child: Text('Nadie todavía.', style: body(context, 14, color: k.ink3))),
      for (final e in _to) ...[
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 6, 8, 6),
          child: Row(children: [
            Expanded(child: Text(e, style: mono(context, 13.5))),
            TextButton(
              onPressed: () {
                setState(() => _to = _to.where((x) => x != e).toList());
                widget.repo.saveRecipients(widget.s.id, _to);
              },
              child: Text('quitar', style: body(context, 13, color: k.ink3)),
            ),
          ]),
        ),
        const Rule(indent: 20),
      ],
      Padding(
        padding: const EdgeInsets.fromLTRB(20, 8, 8, 0),
        child: Row(children: [
          Expanded(child: TextField(controller: _ctrl, keyboardType: TextInputType.emailAddress, onSubmitted: (_) => _add(),
              style: mono(context, 13.5), decoration: const InputDecoration(hintText: 'añadir otro email'))),
          TextButton(onPressed: _add,
              child: Text('añadir', style: body(context, 14, w: FontWeight.w600, color: k.accent))),
        ]),
      ),
      const SizedBox(height: 28),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: InkButton('Enviar parte por email', onTap: _to.isEmpty ? null : _send, busy: _sending),
      ),
      if (st.isNotEmpty)
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
          child: Text(st['ok'] == true
              ? 'Enviado a ${((st['to'] as List?) ?? []).join(', ')}${st['demo'] == true ? ' (demostración, no sale email real)' : ''}.'
              : 'No salió: ${st['error']}',
              style: body(context, 14, w: FontWeight.w500, color: st['ok'] == true ? k.ok : k.danger)),
        ),
    ]);
  }
}
