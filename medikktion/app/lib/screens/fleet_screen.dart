import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../data/app_config.dart';
import '../data/repository.dart';
import '../data/session.dart';
import '../main.dart' show lightMode;
import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/instruments.dart';
import 'session_screen.dart';

class FleetScreen extends StatelessWidget {
  final SessionRepository repo;
  final VoidCallback? onExitDemo;
  const FleetScreen({super.key, required this.repo, this.onExitDemo});

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Scaffold(
      body: SafeArea(
        child: StreamBuilder<List<Session>>(
          stream: repo.sessions(),
          builder: (context, snap) {
            final list = snap.data ?? const <Session>[];
            final live = list.where((s) => s.isLive).length;
            final active = list.fold<int>(0, (a, s) => a + s.activeCount);
            final avg = list.isEmpty ? 0 : (list.fold<int>(0, (a, s) => a + s.health) / list.length).round();
            return CustomScrollView(slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 18, 12, 0),
                  child: Row(children: [
                    const Wordmark(size: 13),
                    const Spacer(),
                    IconButton(
                      tooltip: lightMode.value ? 'Grafito' : 'Porcelana',
                      icon: Icon(lightMode.value ? Icons.dark_mode_outlined : Icons.light_mode_outlined,
                          color: p.text2, size: 20),
                      onPressed: () {
                        lightMode.value = !lightMode.value;
                        AppConfig.setLightTheme(lightMode.value);
                      },
                    ),
                    PopupMenuButton<String>(
                      icon: Icon(Icons.more_horiz, color: p.text2),
                      onSelected: (v) async {
                        if (v == 'demo') onExitDemo?.call();
                        if (v == 'salir') await FirebaseAuth.instance.signOut();
                        if (v == 'codigo') {
                          await AppConfig.clearCode();
                          await FirebaseAuth.instance.signOut();
                        }
                      },
                      itemBuilder: (_) => [
                        if (repo.isDemo) const PopupMenuItem(value: 'demo', child: Text('Salir de la demostración')),
                        if (!repo.isDemo) const PopupMenuItem(value: 'salir', child: Text('Cerrar sesión')),
                        if (!repo.isDemo) const PopupMenuItem(value: 'codigo', child: Text('Cambiar código de activación')),
                      ],
                    ),
                  ]),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 34, 24, 0),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(longDate(DateTime.now()).toUpperCase(), style: label(context)),
                    const SizedBox(height: 10),
                    Text('Flota', style: tx(context, 38, w: FontWeight.w200, h: 1.0)),
                    if (repo.isDemo) ...[
                      const SizedBox(height: 10),
                      Text('Demostración con cuatro máquinas simuladas.', style: tx(context, 13.5, color: p.text3)),
                    ],
                  ]),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 26, 24, 8),
                  child: Panel(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: IntrinsicHeight(
                      child: Row(children: [
                        _kpi(context, '${list.length}', 'Máquinas'),
                        VerticalDivider(color: p.line, width: 1),
                        _kpi(context, '$live', 'En directo', color: live > 0 ? p.gold : null),
                        VerticalDivider(color: p.line, width: 1),
                        _kpi(context, '$active', 'Averías', color: active > 0 ? p.warn : null),
                        VerticalDivider(color: p.line, width: 1),
                        _kpi(context, '$avg', 'Índice', color: list.isEmpty ? null : p.health(avg)),
                      ]),
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(child: SectionLabel('Diagnósticos', padding: const EdgeInsets.fromLTRB(28, 22, 28, 12))),
              if (!snap.hasData)
                const SliverToBoxAdapter(child: Padding(padding: EdgeInsets.all(40),
                    child: Center(child: CircularProgressIndicator(strokeWidth: 1.4))))
              else if (list.isEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(28, 8, 28, 28),
                    child: Text('Sin diagnósticos todavía. Conecte el lector a la máquina e inicie la lectura '
                        'en el portátil: aparecerá aquí al instante.', style: tx(context, 14, color: p.text2, h: 1.55)),
                  ),
                ),
              SliverList.separated(
                itemCount: list.length,
                separatorBuilder: (_, _) => const SizedBox(height: 12),
                itemBuilder: (_, i) => Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: _MachineCard(list[i], repo),
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 40)),
            ]);
          },
        ),
      ),
    );
  }

  Widget _kpi(BuildContext c, String v, String l, {Color? color}) => Expanded(
        child: Column(children: [
          Text(v, style: num_(c, 26, color: color)),
          const SizedBox(height: 6),
          Text(l.toUpperCase(), style: label(c, size: 8.5), textAlign: TextAlign.center),
        ]),
      );
}

class _MachineCard extends StatelessWidget {
  final Session s;
  final SessionRepository repo;
  const _MachineCard(this.s, this.repo);

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final verdict = s.tamper['verdict'] as String?;
    final hours = s.tamper['reported_hours'];
    return Material(
      color: p.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: BorderSide(color: p.line)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.push(context, PageRouteBuilder(
          transitionDuration: const Duration(milliseconds: 320),
          pageBuilder: (_, _, _) => SessionScreen(repo: repo, id: s.id),
          transitionsBuilder: (_, a, _, child) => FadeTransition(opacity: a,
              child: SlideTransition(position: Tween(begin: const Offset(0, 0.02), end: Offset.zero)
                  .animate(CurvedAnimation(parent: a, curve: Curves.easeOutCubic)), child: child)),
        )),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 18, 18, 18),
          child: Row(children: [
            HealthDial(score: s.health, caption: '', size: 78),
            const SizedBox(width: 16),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(s.brand.toUpperCase(), style: label(context, color: p.gold),
                      maxLines: 1, overflow: TextOverflow.ellipsis)),
                  if (s.isLive) const LivePulse() else Text(whenText(s.updatedAt), style: tx(context, 11, color: p.text3)),
                ]),
                const SizedBox(height: 5),
                Text(s.model, style: tx(context, 22, w: FontWeight.w300, h: 1.1)),
                const SizedBox(height: 4),
                Text('${s.machine['machine_class_label'] ?? ''} · ${s.location.split(' · ').first}',
                    style: tx(context, 12.5, color: p.text3), maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 12),
                Wrap(spacing: 14, runSpacing: 6, children: [
                  _fact(context, s.activeCount == 0 ? 'Sin averías' : '${s.activeCount} ${s.activeCount == 1 ? 'avería' : 'averías'}',
                      s.activeCount == 0 ? p.ok : p.severity(s.maxSeverity)),
                  if (hours != null) _fact(context, '${fmtNum(hours, decimals: 0)} h', p.text2),
                  _fact(context, switch (verdict) {
                    'manipulado' => 'Horómetro alterado',
                    'sospechoso' => 'Horómetro dudoso',
                    'ok' => 'Horómetro íntegro',
                    _ => 'Sin datos de horas',
                  }, p.verdict(verdict)),
                ]),
              ]),
            ),
          ]),
        ),
      ),
    );
  }

  Widget _fact(BuildContext c, String t, Color color) => Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 5, height: 5, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(t, style: tx(c, 12, color: c.p.text2, w: FontWeight.w500)),
      ]);
}
