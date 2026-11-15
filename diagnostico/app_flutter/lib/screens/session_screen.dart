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
    if (s == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final tabs = [
      SummaryTab(s: s, goTo: (i) => setState(() => _tab = i)),
      DtcsTab(s: s),
      EcusTab(s: s),
      LiveTab(s: s, history: _history),
      ReportTab(s: s, repo: widget.repo),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(s.title, style: const TextStyle(fontWeight: FontWeight.w800)),
          Text('Nº serie ${s.machine['serial'] ?? '—'}', style: const TextStyle(fontSize: 12, color: Colors.white60)),
        ]),
        actions: [if (s.isLive) const Padding(padding: EdgeInsets.only(right: 12), child: LiveDot())],
      ),
      body: tabs[_tab],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: [
          const NavigationDestination(icon: Icon(Icons.dashboard_outlined), selectedIcon: Icon(Icons.dashboard), label: 'Resumen'),
          NavigationDestination(
              icon: Badge(isLabelVisible: s.activeCount > 0, label: Text('${s.activeCount}'),
                  child: const Icon(Icons.build_outlined)),
              label: 'Averías'),
          const NavigationDestination(icon: Icon(Icons.memory), label: 'Centralitas'),
          const NavigationDestination(icon: Icon(Icons.speed), label: 'En vivo'),
          const NavigationDestination(icon: Icon(Icons.email_outlined), label: 'Informe'),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------- RESUMEN
class SummaryTab extends StatelessWidget {
  final Session s;
  final void Function(int) goTo;
  const SummaryTab({super.key, required this.s, required this.goTo});

  @override
  Widget build(BuildContext context) {
    final sum = s.summary, t = s.tamper, m = s.machine, l = s.lamps;
    final vc = verdictColor(t['verdict'] as String?);
    final critical = s.dtcs.where((d) => d['active'] == true && (d['severity'] as num) >= 4).toList();
    final mods = ((s.modifications['findings'] as List?) ?? []).cast<Map>();
    return ListView(padding: const EdgeInsets.all(16), children: [
      // Testigos
      Row(children: [
        _lamp('Parada', l['red_stop'] == true, const Color(0xFFE53935), Icons.stop_circle),
        _lamp('Aviso', l['amber_warning'] == true, const Color(0xFFFFA000), Icons.warning_amber_rounded),
        _lamp('Emisiones', l['mil'] == true, const Color(0xFFFFA000), Icons.eco),
        _lamp('Protección', l['protect'] == true, const Color(0xFFFFA000), Icons.shield),
      ]),
      const SizedBox(height: 12),
      GridView.count(
        crossAxisCount: 2, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 1.9,
        children: [
          StatTile(label: 'Averías activas', value: '${sum['active_dtcs'] ?? 0}', icon: Icons.error_outline,
              color: severityColors[s.maxSeverity]),
          StatTile(label: 'Averías históricas', value: '${sum['history_dtcs'] ?? 0}', icon: Icons.history),
          StatTile(label: 'Centralitas detectadas', value: '${sum['ecus'] ?? 0}', icon: Icons.memory),
          StatTile(label: 'Coste reparación estimado',
              value: '${fmtNum(sum['repair_cost_min_eur'], decimals: 0)}–${fmtNum(sum['repair_cost_max_eur'], decimals: 0)} €',
              icon: Icons.euro),
        ],
      ),
      const SizedBox(height: 12),
      // Manipulación
      SectionCard(
        title: 'Horas / km · manipulación', icon: Icons.policy, accent: vc,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${t['label'] ?? ''}', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: vc)),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(value: ((t['score'] as num?) ?? 0) / 100, minHeight: 10,
                color: vc, backgroundColor: Colors.white10),
          ),
          const SizedBox(height: 4),
          Text('Puntuación de sospecha ${t['score']}/100 · ${t['checks']} comprobaciones cruzadas',
              style: const TextStyle(fontSize: 11, color: Colors.white54)),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: _kv('Horas que marca', '${fmtNum(t['reported_hours'])} h')),
            if (t['estimated_real_hours'] != null)
              Expanded(child: _kv('Horas reales estimadas', '≈ ${fmtNum(t['estimated_real_hours'], decimals: 0)} h', vc)),
          ]),
          const Divider(height: 22),
          for (final e in ((t['evidence'] as List?) ?? []).cast<Map>()) _evidence(e),
        ]),
      ),
      if (mods.isNotEmpty) ...[
        const SizedBox(height: 12),
        SectionCard(
          title: 'Modificaciones detectadas', icon: Icons.developer_board, accent: const Color(0xFFE53935),
          child: Column(children: [for (final f in mods) _evidence({...f, 'level': f['level']})]),
        ),
      ],
      if (critical.isNotEmpty) ...[
        const SizedBox(height: 12),
        SectionCard(
          title: 'Atención prioritaria', icon: Icons.priority_high, accent: const Color(0xFFFB8C00),
          child: Column(children: [
            for (final d in critical)
              ListTile(
                contentPadding: EdgeInsets.zero, dense: true,
                leading: SeverityBadge((d['severity'] as num).toInt(), compact: true),
                title: Text('${d['name']}', style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text('${d['code']} · ${d['fmi_text']}'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => goTo(1),
              ),
          ]),
        ),
      ],
      const SizedBox(height: 12),
      SectionCard(
        title: 'Máquina', icon: Icons.agriculture,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _row('Marca', '${m['brand_name']}'),
          _row('Modelo', '${m['model']}'),
          _row('Nº serie', '${m['serial']}'),
          _row('Unidad', '${m['unit']}'),
          _row('Tipo', '${m['machine_class_label']}'),
          _row('Conector', '${m['connector']}'),
          _row('Software oficial', '${m['official_software']}'),
          const SizedBox(height: 6),
          Text('${m['brand_note']}', style: const TextStyle(fontSize: 12, color: Colors.white60)),
        ]),
      ),
      const SizedBox(height: 8),
      Text('${sum['frames']} tramas CAN recibidas${s.simulated ? ' · datos simulados' : ''}',
          textAlign: TextAlign.center, style: const TextStyle(fontSize: 11, color: Colors.white38)),
    ]);
  }

  Widget _lamp(String label, bool on, Color c, IconData i) => Expanded(
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 3),
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: on ? c.withValues(alpha: 0.2) : kCard,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: on ? c : Colors.white10),
          ),
          child: Column(children: [
            Icon(i, color: on ? c : Colors.white24),
            const SizedBox(height: 2),
            Text(label, style: TextStyle(fontSize: 10, color: on ? c : Colors.white38, fontWeight: FontWeight.w700)),
          ]),
        ),
      );

  Widget _kv(String k, String v, [Color? c]) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(k, style: const TextStyle(fontSize: 11, color: Colors.white54)),
        Text(v, style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: c)),
      ]);

  Widget _row(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 120, child: Text(k, style: const TextStyle(color: Colors.white54, fontSize: 13))),
          Expanded(child: Text(v.isEmpty || v == 'null' ? '—' : v, style: const TextStyle(fontSize: 13))),
        ]),
      );

  Widget _evidence(Map e) {
    final ok = e['level'] == 'ok';
    final c = ok ? const Color(0xFF43A047) : (e['level'] == 'alta' ? const Color(0xFFE53935) : const Color(0xFFFB8C00));
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(ok ? Icons.check_circle : Icons.warning_rounded, size: 18, color: c),
        const SizedBox(width: 8),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${e['title']}', style: TextStyle(fontWeight: FontWeight.w700, color: c)),
            Text('${e['detail']}', style: const TextStyle(fontSize: 12, color: Colors.white70)),
          ]),
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------- AVERÍAS
class DtcsTab extends StatefulWidget {
  final Session s;
  const DtcsTab({super.key, required this.s});
  @override
  State<DtcsTab> createState() => _DtcsTabState();
}

class _DtcsTabState extends State<DtcsTab> {
  String _filter = 'activas';

  @override
  Widget build(BuildContext context) {
    final all = widget.s.dtcs;
    final list = switch (_filter) {
      'activas' => all.where((d) => d['active'] == true).toList(),
      'historicas' => all.where((d) => d['active'] != true).toList(),
      _ => all,
    };
    return Column(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
        child: SegmentedButton<String>(
          segments: [
            ButtonSegment(value: 'activas', label: Text('Activas (${all.where((d) => d['active'] == true).length})')),
            ButtonSegment(value: 'historicas', label: Text('Históricas (${all.where((d) => d['active'] != true).length})')),
            ButtonSegment(value: 'todas', label: Text('Todas (${all.length})')),
          ],
          selected: {_filter},
          onSelectionChanged: (v) => setState(() => _filter = v.first),
          showSelectedIcon: false,
        ),
      ),
      Expanded(
        child: list.isEmpty
            ? const Center(child: Text('Sin averías en este grupo 👍'))
            : ListView.separated(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                itemCount: list.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (_, i) => DtcCard(d: list[i]),
              ),
      ),
    ]);
  }
}

class DtcCard extends StatelessWidget {
  final Map<String, dynamic> d;
  const DtcCard({super.key, required this.d});

  @override
  Widget build(BuildContext context) {
    final sev = (d['severity'] as num).toInt();
    final c = severityColors[sev]!;
    final parts = ((d['parts'] as List?) ?? []).cast<Map>();
    final causes = ((d['causes'] as List?) ?? []).cast<String>();
    final steps = ((d['steps'] as List?) ?? []).cast<String>();
    return Container(
      decoration: BoxDecoration(color: kCard, borderRadius: BorderRadius.circular(14),
          border: Border(left: BorderSide(color: c, width: 5))),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.fromLTRB(14, 6, 10, 6),
          childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
          expandedCrossAxisAlignment: CrossAxisAlignment.start,
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              SeverityBadge(sev),
              const SizedBox(width: 8),
              Text('${d['code']}', style: const TextStyle(fontSize: 12, color: Colors.white60, fontFamily: 'monospace')),
              const Spacer(),
              if (d['active'] != true)
                const Text('HISTÓRICA', style: TextStyle(fontSize: 10, color: Colors.white38, fontWeight: FontWeight.w700)),
            ]),
            const SizedBox(height: 6),
            Text('${d['name']}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
            Text('${d['fmi_text']}', style: const TextStyle(fontSize: 13, color: Colors.white70)),
            const SizedBox(height: 6),
            Wrap(spacing: 12, runSpacing: 4, children: [
              _mini(Icons.memory, '${d['source_name']}'),
              _mini(Icons.repeat, '${d['occurrences']} veces'),
              _mini(Icons.euro, '${d['cost_min_eur']}–${d['cost_max_eur']} €'),
            ]),
            const SizedBox(height: 6),
            DifficultyDots((d['difficulty'] as num).toInt(), showLabel: false),
          ]),
          children: [
            if (d['warning'] != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(color: const Color(0xFFE53935).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8), border: Border.all(color: const Color(0xFFE53935))),
                child: Row(children: [
                  const Icon(Icons.dangerous, color: Color(0xFFE53935)),
                  const SizedBox(width: 8),
                  Expanded(child: Text('${d['warning']}', style: const TextStyle(fontWeight: FontWeight.w700))),
                ]),
              ),
            _h('Sistema'),
            Text('${d['system']}', style: const TextStyle(color: Colors.white70)),
            if (causes.isNotEmpty) ...[
              _h('Causas probables (de más a menos frecuente)'),
              for (final x in causes) _bullet(x),
            ],
            _h('Solución paso a paso'),
            for (var i = 0; i < steps.length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  CircleAvatar(radius: 11, backgroundColor: kAmber,
                      child: Text('${i + 1}', style: const TextStyle(fontSize: 11, color: Colors.black, fontWeight: FontWeight.w800))),
                  const SizedBox(width: 8),
                  Expanded(child: Text(steps[i])),
                ]),
              ),
            _h('Piezas y coste aproximado'),
            if (parts.isEmpty) const Text('Sin pieza: diagnóstico / ajuste', style: TextStyle(color: Colors.white60)),
            for (final p in parts)
              Container(
                margin: const EdgeInsets.only(bottom: 6),
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(color: kCard2, borderRadius: BorderRadius.circular(8)),
                child: Row(children: [
                  const Icon(Icons.settings, size: 16, color: Colors.white54),
                  const SizedBox(width: 8),
                  Expanded(child: Text('${p['nombre']}')),
                  Text('${p['min']}–${p['max']} €', style: const TextStyle(fontWeight: FontWeight.w800, color: kAmber)),
                ]),
              ),
            const SizedBox(height: 6),
            Row(children: [
              Expanded(child: _box('Mano de obra', '${d['labour_hours']} h')),
              const SizedBox(width: 8),
              Expanded(child: _box('Total estimado', '${d['cost_min_eur']}–${d['cost_max_eur']} €')),
            ]),
            _h('Dificultad de reparación'),
            DifficultyDots((d['difficulty'] as num).toInt()),
            if (d['known'] != true) ...[
              const SizedBox(height: 10),
              Text(d['proprietary'] == true
                  ? 'Código propietario del fabricante: el significado exacto está en su software oficial.'
                  : 'Código no catalogado todavía en la base Horken.',
                  style: const TextStyle(fontSize: 12, color: Colors.orangeAccent)),
            ],
            const SizedBox(height: 8),
            const Text('Costes orientativos: recambio alternativo → original. Verificar referencia por nº de serie.',
                style: TextStyle(fontSize: 11, color: Colors.white38)),
          ],
        ),
      ),
    );
  }

  Widget _mini(IconData i, String t) => Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(i, size: 13, color: Colors.white54),
        const SizedBox(width: 3),
        Flexible(child: Text(t, style: const TextStyle(fontSize: 12, color: Colors.white60))),
      ]);
  Widget _h(String t) => Padding(
      padding: const EdgeInsets.only(top: 12, bottom: 6),
      child: Text(t.toUpperCase(),
          style: const TextStyle(fontSize: 11, letterSpacing: 1, fontWeight: FontWeight.w800, color: kAmber)));
  Widget _bullet(String t) => Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('•  ', style: TextStyle(color: kAmber)),
        Expanded(child: Text(t)),
      ]));
  Widget _box(String k, String v) => Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(color: kCard2, borderRadius: BorderRadius.circular(8)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(k, style: const TextStyle(fontSize: 11, color: Colors.white54)),
          Text(v, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        ]),
      );
}

// ---------------------------------------------------------------- CENTRALITAS
class EcusTab extends StatelessWidget {
  final Session s;
  const EcusTab({super.key, required this.s});

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(16), children: [
      for (final e in s.ecus) ...[
        SectionCard(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(color: kAmber.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(6)),
                child: Text('${e['address_hex']}', style: const TextStyle(fontFamily: 'monospace', color: kAmber, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(width: 10),
              Expanded(child: Text('${e['name']}', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15))),
            ]),
            const SizedBox(height: 10),
            Row(children: [
              _pill('${e['active_dtcs']} activas', (e['active_dtcs'] as num) > 0 ? const Color(0xFFFB8C00) : const Color(0xFF43A047)),
              const SizedBox(width: 6),
              _pill('${e['history_dtcs']} históricas', Colors.white54),
              if (e['engine_hours'] != null) ...[const SizedBox(width: 6), _pill('${fmtNum(e['engine_hours'])} h', Colors.white70)],
            ]),
            const SizedBox(height: 10),
            _kv('Software', ((e['software'] as List?) ?? []).join('\n')),
            if (e['ecu_id'] != null) _kv('Ref. centralita', '${(e['ecu_id'] as Map)['part_number']}'),
            if (e['component'] != null) _kv('Nº serie máquina', '${(e['component'] as Map)['serial']}'),
            if (e['total_revolutions'] != null) _kv('Revoluciones totales', fmtNum(e['total_revolutions'], decimals: 0)),
            if (e['total_fuel_l'] != null) _kv('Combustible total', '${fmtNum(e['total_fuel_l'], decimals: 0)} L'),
            if (e['total_km'] != null) _kv('Distancia total', '${fmtNum(e['total_km'], decimals: 0)} km'),
          ]),
        ),
        const SizedBox(height: 10),
      ],
    ]);
  }

  Widget _pill(String t, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(color: c.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(20)),
        child: Text(t, style: TextStyle(fontSize: 12, color: c, fontWeight: FontWeight.w700)),
      );

  Widget _kv(String k, String v) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 140, child: Text(k, style: const TextStyle(color: Colors.white54, fontSize: 12))),
          Expanded(child: Text(v.isEmpty ? '—' : v, style: const TextStyle(fontSize: 12, fontFamily: 'monospace'))),
        ]),
      );
}

// ---------------------------------------------------------------- EN VIVO
const _limits = <String, List<double?>>{
  // [crítico bajo, aviso bajo, aviso alto, crítico alto]
  'coolant_c': [null, null, 100, 105],
  'oil_pressure_kpa': [100, 200, null, null],
  'hyd_oil_temp_c': [null, null, 85, 95],
  'trans_oil_temp_c': [null, null, 100, 115],
  'oil_temp_c': [null, null, 110, 120],
  'battery_v': [22, 24.5, 29.5, 31],
  'fuel_level_pct': [5, 15, null, null],
  'def_level_pct': [5, 15, null, null],
  'intake_temp_c': [null, null, 65, 80],
};

const _order = ['rpm', 'oil_pressure_kpa', 'coolant_c', 'hyd_oil_temp_c', 'boost_kpa', 'fuel_rate_lh', 'torque_pct',
  'battery_v', 'oil_temp_c', 'trans_oil_temp_c', 'intake_temp_c', 'fuel_level_pct', 'def_level_pct', 'oil_level_pct',
  'coolant_level_pct', 'fuel_temp_c', 'ambient_c'];

class LiveTab extends StatelessWidget {
  final Session s;
  final Map<String, List<double>> history;
  const LiveTab({super.key, required this.s, required this.history});

  Color _color(String k, double v) {
    final l = _limits[k];
    if (l == null) return kAmber;
    if ((l[0] != null && v < l[0]!) || (l[3] != null && v > l[3]!)) return const Color(0xFFE53935);
    if ((l[1] != null && v < l[1]!) || (l[2] != null && v > l[2]!)) return const Color(0xFFFB8C00);
    return const Color(0xFF43A047);
  }

  @override
  Widget build(BuildContext context) {
    final live = s.live;
    final keys = [..._order.where(live.containsKey), ...live.keys.where((k) => !_order.contains(k))];
    final u = s.updatedAt;
    return ListView(padding: const EdgeInsets.all(16), children: [
      Row(children: [
        if (s.isLive) const LiveDot(),
        const SizedBox(width: 8),
        Expanded(child: Text(u == null ? '' : 'Actualizado ${u.hour.toString().padLeft(2, '0')}:'
            '${u.minute.toString().padLeft(2, '0')}:${u.second.toString().padLeft(2, '0')}',
            style: const TextStyle(fontSize: 12, color: Colors.white54))),
      ]),
      const SizedBox(height: 10),
      GridView.builder(
        shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 220, mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 1.25),
        itemCount: keys.length,
        itemBuilder: (_, i) {
          final k = keys[i];
          final p = (live[k] as Map);
          final v = asNum(p['value'])?.toDouble() ?? 0;
          final c = _color(k, v);
          return Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(color: kCard, borderRadius: BorderRadius.circular(12),
                border: Border.all(color: c == kAmber ? Colors.white10 : c.withValues(alpha: 0.6))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${p['label']}', maxLines: 2, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 11, color: Colors.white60)),
              const SizedBox(height: 4),
              Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                Text(fmtNum(v, decimals: v.abs() >= 100 ? 0 : 1),
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: c)),
                const SizedBox(width: 4),
                Padding(padding: const EdgeInsets.only(bottom: 4),
                    child: Text('${p['unit']}', style: const TextStyle(fontSize: 12, color: Colors.white54))),
              ]),
              const Spacer(),
              SizedBox(height: 28, child: Sparkline(history[k] ?? const [], color: c)),
            ]),
          );
        },
      ),
    ]);
  }
}

// ---------------------------------------------------------------- INFORME
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Email no válido')));
      return;
    }
    setState(() {
      if (!_to.contains(e)) _to = [..._to, e];
      _ctrl.clear();
    });
    widget.repo.saveRecipients(widget.s.id, _to);
  }

  Future<void> _send() async {
    if (_to.isEmpty) return;
    setState(() => _sending = true);
    await widget.repo.requestReport(widget.s.id, _to);
    if (!mounted) return;
    setState(() => _sending = false);
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Petición enviada: el portátil genera el PDF y lo manda por email')));
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.s.reportStatus;
    return ListView(padding: const EdgeInsets.all(16), children: [
      SectionCard(
        title: 'Destinatarios del informe', icon: Icons.alternate_email,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (_to.isEmpty) const Text('Añade al menos un correo', style: TextStyle(color: Colors.white54)),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final e in _to)
              InputChip(
                label: Text(e),
                onDeleted: () {
                  setState(() => _to = _to.where((x) => x != e).toList());
                  widget.repo.saveRecipients(widget.s.id, _to);
                },
              ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _ctrl, keyboardType: TextInputType.emailAddress, onSubmitted: (_) => _add(),
                decoration: const InputDecoration(hintText: 'otro@correo.com', isDense: true, border: OutlineInputBorder()),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(onPressed: _add, icon: const Icon(Icons.add)),
          ]),
        ]),
      ),
      const SizedBox(height: 12),
      SizedBox(
        height: 54,
        child: FilledButton.icon(
          onPressed: _sending || _to.isEmpty ? null : _send,
          icon: _sending ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.send),
          label: const Text('Enviar informe completo (PDF)', style: TextStyle(fontWeight: FontWeight.w800)),
        ),
      ),
      if (st.isNotEmpty) ...[
        const SizedBox(height: 12),
        SectionCard(
          accent: st['ok'] == true ? const Color(0xFF43A047) : const Color(0xFFE53935),
          child: Row(children: [
            Icon(st['ok'] == true ? Icons.mark_email_read : Icons.error,
                color: st['ok'] == true ? const Color(0xFF43A047) : const Color(0xFFE53935)),
            const SizedBox(width: 10),
            Expanded(child: Text(st['ok'] == true
                ? 'Informe enviado a ${((st['to'] as List?) ?? []).join(', ')}${st['demo'] == true ? ' (simulado)' : ''}'
                : 'Error al enviar: ${st['error']}')),
          ]),
        ),
      ],
      const SizedBox(height: 16),
      const Text(
        'El informe incluye: datos de la máquina, análisis de horas/km, modificaciones, todas las averías con '
        'causas, pasos, piezas, costes y dificultad, centralitas y últimos valores en vivo.',
        style: TextStyle(fontSize: 12, color: Colors.white54),
      ),
    ]);
  }
}
