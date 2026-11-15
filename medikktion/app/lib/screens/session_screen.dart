import 'dart:async';

import 'package:flutter/material.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import '../widgets/instruments.dart';

class SessionScreen extends StatefulWidget {
  final SessionRepository repo;
  final String id;
  const SessionScreen({super.key, required this.repo, required this.id});
  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> {
  Session? _s;
  StreamSubscription? _sub;

  @override
  void initState() {
    super.initState();
    _sub = widget.repo.session(widget.id).listen((s) {
      if (s != null && mounted) setState(() => _s = s);
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
    final p = context.p;
    if (s == null) return const Scaffold(body: Center(child: CircularProgressIndicator(strokeWidth: 1.4)));
    final tabs = ['Resumen', 'Medidas', 'Averías', 'Centralitas', 'Informe'];
    return DefaultTabController(
      length: tabs.length,
      child: Scaffold(
        appBar: AppBar(
          toolbarHeight: 64,
          leading: IconButton(icon: Icon(Icons.arrow_back_ios_new_rounded, size: 18, color: p.text2),
              onPressed: () => Navigator.pop(context)),
          titleSpacing: 0,
          title: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(s.brand.toUpperCase(), style: label(context, color: p.gold, size: 10)),
            const SizedBox(height: 3),
            Text(s.model, style: tx(context, 20, w: FontWeight.w300)),
          ]),
          actions: [
            if (s.isLive) const Padding(padding: EdgeInsets.only(right: 18), child: LivePulse()),
          ],
          bottom: PreferredSize(
            preferredSize: const Size.fromHeight(46),
            child: Container(
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
              child: TabBar(
                isScrollable: true,
                tabAlignment: TabAlignment.start,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                dividerColor: Colors.transparent,
                indicator: UnderlineTabIndicator(borderSide: BorderSide(color: p.gold, width: 1.6),
                    insets: const EdgeInsets.symmetric(horizontal: 4)),
                labelColor: p.text,
                unselectedLabelColor: p.text3,
                labelStyle: label(context, size: 10.5),
                unselectedLabelStyle: label(context, size: 10.5),
                overlayColor: WidgetStateProperty.all(Colors.transparent),
                tabs: [
                  for (final t in tabs)
                    Tab(height: 44, text: t == 'Averías' && s.activeCount > 0 ? 'AVERÍAS · ${s.activeCount}' : t.toUpperCase()),
                ],
              ),
            ),
          ),
        ),
        body: TabBarView(children: [
          SummaryTab(s: s),
          MeasuresTab(s: s),
          FaultsTab(s: s),
          EcusTab(s: s),
          ReportTab(s: s, repo: widget.repo),
        ]),
      ),
    );
  }
}

EdgeInsets get _page => const EdgeInsets.fromLTRB(20, 20, 20, 40);

// ═══════════════════════════════════════════════════════════════════ RESUMEN
class SummaryTab extends StatelessWidget {
  final Session s;
  const SummaryTab({super.key, required this.s});

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final sum = s.summary, t = s.tamper, m = s.machine, l = s.lamps;
    final verdict = t['verdict'] as String?;
    final vc = p.verdict(verdict);
    final urgent = s.dtcs.where((d) => d['active'] == true && (d['severity'] as num) >= 4).toList();
    final mods = ((s.modifications['findings'] as List?) ?? []).cast<Map>();
    final evidence = ((t['evidence'] as List?) ?? []).cast<Map>();
    final hourEcus = s.ecus.where((e) => e['engine_hours'] != null).toList();

    return ListView(padding: _page, children: [
      // Cabecera: índice de estado + datos de la sesión
      Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        HealthDial(score: s.health, caption: s.healthLabel, size: 150),
        const SizedBox(width: 18),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('ÍNDICE DE ESTADO', style: label(context)),
            const SizedBox(height: 10),
            _meta(context, s.isLive ? 'En directo · ${durText(s.duration)}' : 'Finalizada · ${durText(s.duration)}',
                s.isLive ? p.gold : p.text2),
            _meta(context, s.reference, p.text3, mono_: true),
            if (s.purpose.isNotEmpty) _meta(context, s.purpose, p.text2),
            if (s.location.isNotEmpty) _meta(context, s.location, p.text3),
          ]),
        ),
      ]),
      const SizedBox(height: 22),
      // Cifras
      Row(children: [
        Expanded(child: _kpi(context, '${sum['active_dtcs'] ?? 0}', 'Activas',
            color: s.activeCount > 0 ? p.severity(s.maxSeverity) : p.ok)),
        const SizedBox(width: 10),
        Expanded(child: _kpi(context, '${sum['history_dtcs'] ?? 0}', 'Históricas')),
        const SizedBox(width: 10),
        Expanded(child: _kpi(context, '${sum['ecus'] ?? 0}', 'Centralitas')),
      ]),
      const SizedBox(height: 10),
      Panel(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('COSTE ESTIMADO DE REPARACIÓN', style: label(context, size: 9.5)),
            const SizedBox(height: 8),
            Text(euros(sum['repair_cost_min_eur'], sum['repair_cost_max_eur']), style: num_(context, 24)),
          ])),
          Text('piezas + mano\nde obra', textAlign: TextAlign.right, style: tx(context, 11, color: p.text3)),
        ]),
      ),

      // Testigos
      const SectionLabel('Testigos del cuadro'),
      Panel(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        child: Row(children: [
          _lamp(context, 'Parada', l['red_stop'] == true, p.danger),
          _lamp(context, 'Aviso', l['amber_warning'] == true, p.warn),
          _lamp(context, 'Emisiones', l['mil'] == true, p.warn),
          _lamp(context, 'Protección', l['protect'] == true, p.warn),
        ]),
      ),

      // Horómetro
      const SectionLabel('Integridad del horómetro'),
      Panel(
        border: verdict == 'manipulado' ? p.danger.withValues(alpha: 0.45) : null,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(verdict == 'ok' ? Icons.verified_outlined : Icons.report_gmailerrorred_outlined, color: vc, size: 22),
            const SizedBox(width: 10),
            Expanded(child: Text('${t['label'] ?? 'Sin datos'}', style: tx(context, 17, w: FontWeight.w500, color: vc))),
          ]),
          const SizedBox(height: 6),
          Text('${t['checks'] ?? 0} comprobaciones cruzadas · índice de sospecha ${t['score'] ?? 0}/100',
              style: tx(context, 12, color: p.text3)),
          const SizedBox(height: 20),
          Row(children: [
            Expanded(child: _big(context, 'HORAS QUE MARCA', '${fmtNum(t['reported_hours'])} h', p.text)),
            if (t['estimated_real_hours'] != null)
              Expanded(child: _big(context, 'HORAS REALES ESTIMADAS', '≈ ${fmtNum(t['estimated_real_hours'], decimals: 0)} h', vc)),
          ]),
          if (hourEcus.length > 1) ...[
            const SizedBox(height: 22),
            Text('REGISTRO POR CENTRALITA', style: label(context, size: 9.5)),
            const SizedBox(height: 12),
            HoursBars(items: [for (final e in hourEcus) ('${e['name']}', (e['engine_hours'] as num).toDouble())],
                estimated: (t['estimated_real_hours'] as num?)?.toDouble()),
          ],
          const SizedBox(height: 8),
          Divider(color: p.line, height: 24),
          for (final e in evidence) _evidence(context, e),
        ]),
      ),

      if (mods.isNotEmpty) ...[
        const SectionLabel('Modificaciones detectadas'),
        Panel(
          border: p.danger.withValues(alpha: 0.45),
          child: Column(children: [for (final f in mods) _evidence(context, f)]),
        ),
      ],

      if (urgent.isNotEmpty) ...[
        const SectionLabel('Atención prioritaria'),
        Panel(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Column(children: [
            for (var i = 0; i < urgent.length; i++) ...[
              if (i > 0) Divider(color: p.line, height: 1, indent: 18, endIndent: 18),
              Padding(
                padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  SeverityTag((urgent[i]['severity'] as num).toInt()),
                  const SizedBox(height: 8),
                  Text('${urgent[i]['name']}', style: tx(context, 15.5, w: FontWeight.w500)),
                  const SizedBox(height: 3),
                  Text(urgent[i]['warning'] != null ? '${urgent[i]['warning']}' : '${urgent[i]['fmi_text']}',
                      style: tx(context, 13, color: urgent[i]['warning'] != null ? p.danger : p.text2)),
                ]),
              ),
            ],
          ]),
        ),
      ],

      const SectionLabel('Ficha técnica'),
      Panel(
        child: Column(children: [
          _kv(context, 'Fabricante', '${m['brand_name'] ?? ''}'),
          _kv(context, 'Modelo', '${m['model'] ?? ''}'),
          _kv(context, 'Tipo', '${m['machine_class_label'] ?? ''}'),
          _kv(context, 'Nº de serie', '${m['serial'] ?? ''}', mono_: true),
          if ('${m['vin'] ?? ''}'.isNotEmpty) _kv(context, 'VIN', '${m['vin']}', mono_: true),
          _kv(context, 'Protocolos', s.protocols.join(' · ')),
          _kv(context, 'Conector', '${m['connector'] ?? ''}'),
          _kv(context, 'Software oficial', '${m['official_software'] ?? ''}', last: true),
        ]),
      ),
      const SizedBox(height: 18),
      Text('${m['brand_note'] ?? ''}', style: tx(context, 12.5, color: p.text3, h: 1.55)),
      const SizedBox(height: 14),
      Text('${fmtNum(sum['frames'], decimals: 0)} tramas CAN analizadas${s.simulated ? ' · máquina simulada' : ''}',
          style: tx(context, 11, color: p.text3)),
    ]);
  }

  Widget _meta(BuildContext c, String t, Color color, {bool mono_ = false}) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(t, style: mono_ ? mono(c, 11.5, color: color) : tx(c, 13, color: color),
            maxLines: 2, overflow: TextOverflow.ellipsis),
      );

  Widget _kpi(BuildContext c, String v, String l, {Color? color}) => Panel(
        padding: const EdgeInsets.fromLTRB(16, 16, 12, 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(v, style: num_(c, 30, color: color)),
          const SizedBox(height: 8),
          Text(l.toUpperCase(), style: label(c, size: 8.5), maxLines: 1, overflow: TextOverflow.ellipsis),
        ]),
      );

  Widget _big(BuildContext c, String k, String v, Color color) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(k, style: label(c, size: 9)),
        const SizedBox(height: 8),
        FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: Text(v, style: num_(c, 26, color: color))),
      ]);

  Widget _lamp(BuildContext c, String l, bool on, Color color) => Expanded(
        child: Column(children: [
          Container(
            width: 10, height: 10,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: on ? color : Colors.transparent,
              border: Border.all(color: on ? color : c.p.line2, width: 1.2),
              boxShadow: on ? [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 10)] : null,
            ),
          ),
          const SizedBox(height: 8),
          Text(l.toUpperCase(), style: label(c, size: 8.5, color: on ? c.p.text : c.p.text3)),
        ]),
      );

  Widget _evidence(BuildContext c, Map e) {
    final p = c.p;
    final ok = e['level'] == 'ok';
    final color = ok ? p.ok : (e['level'] == 'alta' ? p.danger : p.warn);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(padding: const EdgeInsets.only(top: 2),
            child: Icon(ok ? Icons.check_rounded : Icons.priority_high_rounded, size: 15, color: color)),
        const SizedBox(width: 10),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('${e['title']}', style: tx(c, 14, w: FontWeight.w500)),
          const SizedBox(height: 3),
          Text('${e['detail']}', style: tx(c, 12.5, color: p.text2, h: 1.5)),
        ])),
      ]),
    );
  }

  Widget _kv(BuildContext c, String k, String v, {bool mono_ = false, bool last = false}) => Container(
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration: BoxDecoration(border: last ? null : Border(bottom: BorderSide(color: c.p.line))),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 120, child: Text(k, style: tx(c, 12.5, color: c.p.text3))),
          Expanded(child: Text(v.isEmpty || v == 'null' ? '—' : v,
              style: mono_ ? mono(c, 12.5, color: c.p.text) : tx(c, 13.5))),
        ]),
      );
}

// ═══════════════════════════════════════════════════════════════════ MEDIDAS
class MeasuresTab extends StatelessWidget {
  final Session s;
  const MeasuresTab({super.key, required this.s});

  double? _v(String k) {
    final p = s.live[k];
    if (p is! Map) return null;
    final n = asNum(p['value']);
    return n == null ? null : measures[k]?.convert(n) ?? n.toDouble();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final u = s.updatedAt;
    final thermos = ['coolant_c', 'oil_temp_c', 'hyd_oil_temp_c', 'trans_oil_temp_c'].where((k) => _v(k) != null).toList();
    final readouts = ['boost_kpa', 'fuel_rate_lh', 'battery_v', 'torque_pct', 'fuel_level_pct', 'def_level_pct',
      'intake_temp_c', 'ambient_c'].where((k) => _v(k) != null).toList();
    final extra = s.live.keys.where((k) => !measures.containsKey(k)).toList();
    final trends = ['hyd_oil_temp_c', 'coolant_c', 'oil_pressure_kpa', 'rpm', 'trans_oil_temp_c', 'oil_temp_c', 'boost_kpa']
        .where((k) => s.trend[k] is Map).toList();

    return ListView(padding: _page, children: [
      Row(children: [
        if (s.isLive) const LivePulse(text: 'LECTURA EN CURSO') else Text('ÚLTIMA LECTURA', style: label(context)),
        const Spacer(),
        if (u != null) Text('${hhmm(u)}:${u.second.toString().padLeft(2, '0')}', style: mono(context, 12)),
      ]),
      const SizedBox(height: 16),
      if (_v('rpm') != null || _v('oil_pressure_kpa') != null)
        Row(children: [
          if (_v('rpm') != null)
            Expanded(child: Dial(m: measures['rpm']!, value: _v('rpm')!, majorStep: 500,
                tickLabel: (v) => fmtNum(v / 1000, decimals: v % 1000 == 0 ? 0 : 1))),
          if (_v('rpm') != null && _v('oil_pressure_kpa') != null) const SizedBox(width: 10),
          if (_v('oil_pressure_kpa') != null)
            Expanded(child: Dial(m: measures['oil_pressure_kpa']!, value: _v('oil_pressure_kpa')!, majorStep: 1)),
        ]),
      if (thermos.isNotEmpty) ...[
        const SectionLabel('Temperaturas'),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (var i = 0; i < thermos.length && i < 3; i++) ...[
            if (i > 0) const SizedBox(width: 10),
            Expanded(child: Thermometer(m: measures[thermos[i]]!, value: _v(thermos[i])!, height: 200)),
          ],
        ]),
        if (thermos.length > 3) ...[
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: Thermometer(m: measures[thermos[3]]!, value: _v(thermos[3])!, height: 160)),
            const Expanded(flex: 2, child: SizedBox()),
          ]),
        ],
      ],
      if (readouts.isNotEmpty) ...[
        const SectionLabel('Motor y consumos'),
        GridView.count(
          crossAxisCount: 2, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 2.05,
          children: [for (final k in readouts) Readout(m: measures[k]!, value: _v(k)!)],
        ),
      ],
      if (extra.isNotEmpty) ...[
        const SectionLabel('Señales del fabricante'),
        GridView.count(
          crossAxisCount: 2, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10, crossAxisSpacing: 10, childAspectRatio: 2.05,
          children: [
            for (final k in extra)
              Readout(m: measureFor(k, s.live[k] as Map), value: (asNum((s.live[k] as Map)['value']) ?? 0).toDouble()),
          ],
        ),
      ],
      if (trends.isNotEmpty) ...[
        SectionLabel('Tendencias', trailing: Text('muestra cada 5 s', style: tx(context, 11, color: p.text3))),
        for (final k in trends) ...[
          Builder(builder: (context) {
            final tr = s.trend[k] as Map;
            final m = measures[k]!;
            return TrendChart(
              m: m,
              t: [for (final x in (tr['t'] as List)) (x as num).toDouble()],
              v: [for (final x in (tr['v'] as List)) m.convert(x as num)],
            );
          }),
          const SizedBox(height: 10),
        ],
      ],
    ]);
  }
}

// ═══════════════════════════════════════════════════════════════════ AVERÍAS
class FaultsTab extends StatefulWidget {
  final Session s;
  const FaultsTab({super.key, required this.s});
  @override
  State<FaultsTab> createState() => _FaultsTabState();
}

class _FaultsTabState extends State<FaultsTab> {
  int _filter = 0;
  String? _open;

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final all = widget.s.dtcs;
    final act = all.where((d) => d['active'] == true).toList();
    final his = all.where((d) => d['active'] != true).toList();
    final list = [act, his, all][_filter];
    _open ??= list.isNotEmpty ? _key(list.first) : null;
    return ListView(padding: _page, children: [
      Container(
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(color: p.surface, borderRadius: BorderRadius.circular(12), border: Border.all(color: p.line)),
        child: Row(children: [
          _seg(context, 'Activas', act.length, 0),
          _seg(context, 'Históricas', his.length, 1),
          _seg(context, 'Todas', all.length, 2),
        ]),
      ),
      const SizedBox(height: 16),
      if (list.isEmpty)
        Panel(child: Row(children: [
          Icon(Icons.verified_outlined, color: p.ok),
          const SizedBox(width: 12),
          Expanded(child: Text(_filter == 0 ? 'Ninguna avería activa.' : 'Sin registros.',
              style: tx(context, 14, color: p.text2))),
        ])),
      for (final d in list) ...[
        _FaultCard(d: d, open: _open == _key(d), onTap: () => setState(() => _open = _open == _key(d) ? '' : _key(d))),
        const SizedBox(height: 10),
      ],
    ]);
  }

  String _key(Map d) => '${d['source']}|${d['code']}';

  Widget _seg(BuildContext c, String t, int n, int i) {
    final p = c.p;
    final sel = _filter == i;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() {
          _filter = i;
          _open = null;
        }),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 11),
          decoration: BoxDecoration(color: sel ? p.surface2 : Colors.transparent, borderRadius: BorderRadius.circular(9),
              border: Border.all(color: sel ? p.line2 : Colors.transparent)),
          child: Text('${t.toUpperCase()}  $n', textAlign: TextAlign.center,
              style: label(c, size: 10, color: sel ? p.text : p.text3)),
        ),
      ),
    );
  }
}

class _FaultCard extends StatelessWidget {
  final Map<String, dynamic> d;
  final bool open;
  final VoidCallback onTap;
  const _FaultCard({required this.d, required this.open, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final sev = (d['severity'] as num).toInt();
    final c = p.severity(sev);
    final parts = ((d['parts'] as List?) ?? []).cast<Map>();
    final causes = ((d['causes'] as List?) ?? []).cast<String>();
    final steps = ((d['steps'] as List?) ?? []).cast<String>();
    final occ = (d['occurrences'] as num?)?.toInt() ?? 0;
    return Material(
      color: p.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: open ? p.line2 : p.line)),
      clipBehavior: Clip.antiAlias,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        InkWell(
          onTap: onTap,
          child: IntrinsicHeight(
            child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Container(width: 3, color: d['active'] == true ? c : p.line2),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 12, 16),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      SeverityTag(sev),
                      const Spacer(),
                      Text('${d['code']}', style: mono(context, 11)),
                    ]),
                    const SizedBox(height: 10),
                    Text('${d['name']}', style: tx(context, 17, w: FontWeight.w400, h: 1.25)),
                    const SizedBox(height: 4),
                    Text('${d['fmi_text']}', style: tx(context, 13, color: p.text2)),
                    const SizedBox(height: 10),
                    Text([
                      '${d['source_name']}',
                      if (occ > 0) '$occ ${occ == 1 ? 'ocurrencia' : 'ocurrencias'}',
                      if (d['active'] != true) 'histórica',
                      if (d['protocol'] != null && d['protocol'] != 'J1939') '${d['protocol']}',
                    ].join('  ·  '), style: tx(context, 11.5, color: p.text3)),
                  ]),
                ),
              ),
              Padding(padding: const EdgeInsets.only(right: 12),
                  child: Icon(open ? Icons.expand_less_rounded : Icons.expand_more_rounded, color: p.text3, size: 20)),
            ]),
          ),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 240),
          curve: Curves.easeOutCubic,
          alignment: Alignment.topCenter,
          child: !open ? const SizedBox(width: double.infinity) : Container(
            width: double.infinity,
            decoration: BoxDecoration(border: Border(top: BorderSide(color: p.line))),
            padding: const EdgeInsets.fromLTRB(19, 18, 19, 20),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (d['warning'] != null)
                Container(
                  width: double.infinity, margin: const EdgeInsets.only(bottom: 18),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(color: p.danger.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: p.danger.withValues(alpha: 0.4))),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Icon(Icons.warning_amber_rounded, color: p.danger, size: 18),
                    const SizedBox(width: 10),
                    Expanded(child: Text('${d['warning']}', style: tx(context, 13.5, w: FontWeight.w500, color: p.danger))),
                  ]),
                ),
              if (causes.isNotEmpty) ...[
                Text('CAUSAS PROBABLES', style: label(context, size: 9.5)),
                const SizedBox(height: 10),
                for (final x in causes) Padding(
                  padding: const EdgeInsets.only(bottom: 7),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Padding(padding: const EdgeInsets.only(top: 7),
                        child: Container(width: 4, height: 4, decoration: BoxDecoration(color: p.gold, shape: BoxShape.circle))),
                    const SizedBox(width: 10),
                    Expanded(child: Text(x, style: tx(context, 13.5, color: p.text2))),
                  ]),
                ),
                const SizedBox(height: 14),
              ],
              Text('PROCEDIMIENTO', style: label(context, size: 9.5)),
              const SizedBox(height: 10),
              for (var i = 0; i < steps.length; i++) Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    width: 22, height: 22, alignment: Alignment.center,
                    decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: p.goldDim)),
                    child: Text('${i + 1}', style: tx(context, 10.5, color: p.gold, w: FontWeight.w600)),
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Padding(padding: const EdgeInsets.only(top: 2),
                      child: Text(steps[i], style: tx(context, 13.5, h: 1.45)))),
                ]),
              ),
              const SizedBox(height: 14),
              Text('PIEZAS Y PRESUPUESTO', style: label(context, size: 9.5)),
              const SizedBox(height: 8),
              if (parts.isEmpty) Text('No requiere sustitución de piezas.', style: tx(context, 13.5, color: p.text2)),
              for (final pt in parts) Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
                child: Row(children: [
                  Expanded(child: Text('${pt['nombre']}', style: tx(context, 13.5))),
                  Text(euros(pt['min'], pt['max']), style: tx(context, 13, w: FontWeight.w500)),
                ]),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Row(children: [
                  Expanded(child: Text('Mano de obra · ${fmtNum(d['labour_hours'])} h', style: tx(context, 13, color: p.text2))),
                ]),
              ),
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(color: p.surface2, borderRadius: BorderRadius.circular(10)),
                child: Row(children: [
                  Text('TOTAL ESTIMADO', style: label(context, size: 9.5)),
                  const Spacer(),
                  Text(euros(d['cost_min_eur'], d['cost_max_eur']), style: tx(context, 16, w: FontWeight.w500, color: p.gold)),
                ]),
              ),
              const SizedBox(height: 18),
              Text('DIFICULTAD DE REPARACIÓN', style: label(context, size: 9.5)),
              const SizedBox(height: 10),
              DifficultyScale((d['difficulty'] as num).toInt()),
              const SizedBox(height: 16),
              if (d['name_language'] == 'en')
                Text('Descripción oficial SAE en inglés.', style: tx(context, 11.5, color: p.text3)),
              if (d['known'] != true)
                Text(d['proprietary'] == true
                    ? 'Código propietario: su definición exacta figura en el software oficial del fabricante.'
                    : 'Código pendiente de catalogar.', style: tx(context, 12, color: p.warn)),
              Text('Precios orientativos (recambio alternativo – original). Verificar referencia por número de serie.',
                  style: tx(context, 11.5, color: p.text3, h: 1.5)),
            ]),
          ),
        ),
      ]),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════ CENTRALITAS
class EcusTab extends StatelessWidget {
  final Session s;
  const EcusTab({super.key, required this.s});

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return ListView(padding: _page, children: [
      Text('${s.ecus.length} unidades de control han respondido', style: tx(context, 14, color: p.text2)),
      const SizedBox(height: 16),
      for (final e in s.ecus) ...[
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text('${e['address_hex']}', style: mono(context, 11.5, color: p.gold)),
              const Spacer(),
              Text('${e['protocol'] ?? ''}', style: label(context, size: 9)),
            ]),
            const SizedBox(height: 8),
            Text('${e['name']}', style: tx(context, 17, w: FontWeight.w400)),
            const SizedBox(height: 12),
            Row(children: [
              _chip(context, (e['active_dtcs'] as num) == 0 ? 'Sin averías activas' : '${e['active_dtcs']} activas',
                  (e['active_dtcs'] as num) > 0 ? p.warn : p.ok),
              if ((e['history_dtcs'] as num) > 0) _chip(context, '${e['history_dtcs']} históricas', p.text3),
            ]),
            const SizedBox(height: 12),
            if (e['engine_hours'] != null) _row(context, 'Horómetro', '${fmtNum(e['engine_hours'])} h'),
            if (e['total_revolutions'] != null) _row(context, 'Revoluciones', fmtNum(e['total_revolutions'], decimals: 0)),
            if (e['total_fuel_l'] != null) _row(context, 'Combustible total', '${fmtNum(e['total_fuel_l'], decimals: 0)} L'),
            if (e['total_km'] != null) _row(context, 'Distancia', '${fmtNum(e['total_km'], decimals: 0)} km'),
            for (final sw in ((e['software'] as List?) ?? [])) _row(context, 'Software', '$sw', mono_: true),
            for (final cal in ((e['calibrations'] as List?) ?? []).cast<Map>())
              _row(context, 'Calibración', '${cal['cal_id']} · CVN ${cal['cvn']}', mono_: true),
            if (e['ecu_id'] is Map && '${(e['ecu_id'] as Map)['part_number'] ?? ''}'.isNotEmpty)
              _row(context, 'Referencia', '${(e['ecu_id'] as Map)['part_number']}', mono_: true),
          ]),
        ),
        const SizedBox(height: 10),
      ],
    ]);
  }

  Widget _chip(BuildContext c, String t, Color color) => Padding(
        padding: const EdgeInsets.only(right: 14),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Container(width: 5, height: 5, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(t, style: tx(c, 12, color: c.p.text2, w: FontWeight.w500)),
        ]),
      );

  Widget _row(BuildContext c, String k, String v, {bool mono_ = false}) => Padding(
        padding: const EdgeInsets.only(top: 7),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 118, child: Text(k, style: tx(c, 12, color: c.p.text3))),
          Expanded(child: Text(v, style: mono_ ? mono(c, 11.5, color: c.p.text2) : tx(c, 13))),
        ]),
      );
}

// ═══════════════════════════════════════════════════════════════════ INFORME
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dirección de correo no válida')));
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
        const SnackBar(content: Text('Solicitado. El equipo de lectura genera el informe y lo envía.')));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final st = widget.s.reportStatus;
    return ListView(padding: _page, children: [
      Text('Informe técnico', style: tx(context, 26, w: FontWeight.w300)),
      const SizedBox(height: 10),
      Text('Documento PDF con el índice de estado, la integridad del horómetro, cada avería con su procedimiento, '
          'piezas y presupuesto, las unidades de control y las mediciones registradas.',
          style: tx(context, 13.5, color: p.text2, h: 1.55)),
      const SectionLabel('Destinatarios'),
      Panel(
        padding: const EdgeInsets.fromLTRB(18, 8, 8, 8),
        child: Column(children: [
          if (_to.isEmpty)
            Padding(padding: const EdgeInsets.symmetric(vertical: 12),
                child: Align(alignment: Alignment.centerLeft,
                    child: Text('Sin destinatarios.', style: tx(context, 13.5, color: p.text3)))),
          for (final e in _to)
            Container(
              decoration: BoxDecoration(border: Border(bottom: BorderSide(color: p.line))),
              child: Row(children: [
                Expanded(child: Text(e, style: tx(context, 14))),
                IconButton(
                  icon: Icon(Icons.close_rounded, size: 18, color: p.text3),
                  onPressed: () {
                    setState(() => _to = _to.where((x) => x != e).toList());
                    widget.repo.saveRecipients(widget.s.id, _to);
                  },
                ),
              ]),
            ),
          Row(children: [
            Expanded(child: TextField(
              controller: _ctrl, keyboardType: TextInputType.emailAddress, onSubmitted: (_) => _add(),
              style: tx(context, 14),
              decoration: const InputDecoration(hintText: 'Añadir correo', filled: false, border: InputBorder.none,
                  enabledBorder: InputBorder.none, focusedBorder: InputBorder.none, contentPadding: EdgeInsets.zero),
            )),
            IconButton(icon: Icon(Icons.add_rounded, color: p.gold), onPressed: _add),
          ]),
        ]),
      ),
      const SizedBox(height: 22),
      GoldButton('Enviar informe', onTap: _to.isEmpty ? null : _send, busy: _sending),
      if (st.isNotEmpty) ...[
        const SizedBox(height: 16),
        Panel(
          border: (st['ok'] == true ? p.ok : p.danger).withValues(alpha: 0.45),
          child: Row(children: [
            Icon(st['ok'] == true ? Icons.mark_email_read_outlined : Icons.error_outline,
                color: st['ok'] == true ? p.ok : p.danger, size: 20),
            const SizedBox(width: 12),
            Expanded(child: Text(st['ok'] == true
                ? 'Enviado a ${((st['to'] as List?) ?? []).join(', ')}${st['demo'] == true ? ' (demostración)' : ''}'
                : 'No se pudo enviar: ${st['error']}', style: tx(context, 13.5, color: p.text2))),
          ]),
        ),
      ],
    ]);
  }
}
