import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../data/app_config.dart';
import '../data/repository.dart';
import '../data/session.dart';
import '../main.dart' show nightMode;
import '../theme.dart';
import '../widgets/common.dart';
import 'session_screen.dart';

class SessionsScreen extends StatelessWidget {
  final SessionRepository repo;
  final VoidCallback? onExitDemo;
  const SessionsScreen({super.key, required this.repo, this.onExitDemo});

  String _greeting() {
    final h = DateTime.now().hour;
    return h < 13 ? 'Buenos días' : (h < 21 ? 'Buenas tardes' : 'Buenas noches');
  }

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final user = repo.isDemo ? null : FirebaseAuth.instance.currentUser?.email;
    return Scaffold(
      body: SafeArea(
        child: StreamBuilder<List<Session>>(
          stream: repo.sessions(),
          builder: (context, snap) {
            final list = snap.data ?? const <Session>[];
            final live = list.where((s) => s.isLive).length;
            return ListView(padding: EdgeInsets.zero, children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 8, 0),
                child: Row(children: [
                  Text('HORKEN', style: cond(context, 26, w: FontWeight.w700, ls: 4)),
                  const Spacer(),
                  IconButton(
                    tooltip: nightMode.value ? 'Modo día' : 'Modo noche',
                    icon: Icon(nightMode.value ? Icons.light_mode_outlined : Icons.dark_mode_outlined, color: k.ink2),
                    onPressed: () {
                      nightMode.value = !nightMode.value;
                      AppConfig.setNightTheme(nightMode.value);
                    },
                  ),
                  PopupMenuButton<String>(
                    icon: Icon(Icons.more_vert, color: k.ink2),
                    color: k.paper2,
                    onSelected: (v) async {
                      if (v == 'salir') await FirebaseAuth.instance.signOut();
                      if (v == 'demo') onExitDemo?.call();
                      if (v == 'codigo') {
                        await AppConfig.clearCode();
                        await FirebaseAuth.instance.signOut();
                      }
                    },
                    itemBuilder: (_) => [
                      if (repo.isDemo) const PopupMenuItem(value: 'demo', child: Text('Salir de la demostración')),
                      if (!repo.isDemo) const PopupMenuItem(value: 'salir', child: Text('Cerrar sesión')),
                      if (!repo.isDemo) const PopupMenuItem(value: 'codigo', child: Text('Cambiar código de configuración')),
                    ],
                  ),
                ]),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 2, 20, 18),
                child: Text(
                  repo.isDemo
                      ? 'Máquinas de prueba del simulador. Así se verán las reales.'
                      : '${_greeting()}${user != null ? ', ${user.split('@').first}' : ''}. '
                        '${live > 0 ? '$live máquina${live > 1 ? 's' : ''} conectada${live > 1 ? 's' : ''} ahora.' : 'Ninguna máquina conectada ahora.'}',
                  style: body(context, 15, color: k.ink2),
                ),
              ),
              const Rule(strong: true),
              if (!snap.hasData)
                const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator()))
              else if (list.isEmpty)
                Padding(
                  padding: const EdgeInsets.all(28),
                  child: Text('Todavía no hay ninguna lectura.\nEnchufa el lector a la máquina y abre '
                      '"diagnostico.bat" en el portátil: aparecerá aquí al momento.',
                      style: body(context, 15, color: k.ink2)),
                ),
              for (final s in list) _SessionRow(s, repo),
              const SizedBox(height: 30),
            ]);
          },
        ),
      ),
    );
  }
}

class _SessionRow extends StatelessWidget {
  final Session s;
  final SessionRepository repo;
  const _SessionRow(this.s, this.repo);

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final t = s.tamper;
    final verdict = t['verdict'] as String?;
    final d = s.updatedAt;
    final hours = t['reported_hours'];
    final facts = <String>[
      s.activeCount == 0 ? 'sin averías activas' : '${s.activeCount} avería${s.activeCount > 1 ? 's' : ''} activa${s.activeCount > 1 ? 's' : ''}',
      if (hours != null) '${fmtNum(hours, decimals: 0)} h',
      if (s.machine['vin'] != null && '${s.machine['vin']}'.isNotEmpty && hours == null) 'VIN ${s.machine['vin']}',
    ];
    final verdictText = switch (verdict) {
      'manipulado' => 'horas/km manipulados',
      'sospechoso' => 'horas/km dudosos',
      'ok' => 'horas/km correctos',
      _ => null,
    };
    return InkWell(
      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => SessionScreen(repo: repo, id: s.id))),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 16, 16),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  if (s.isLive) const LiveMark() else Text(whenText(d), style: mono(context, 11, color: k.ink3)),
                  if (s.location.isNotEmpty) Text('  ·  ${s.location}', style: mono(context, 11, color: k.ink3)),
                ]),
                const SizedBox(height: 4),
                Text(s.title.toUpperCase(), style: cond(context, 22, w: FontWeight.w700, ls: 0.5)),
                Text('${s.machine['machine_class_label'] ?? ''} · nº ${s.machine['serial'] ?? '—'}',
                    style: body(context, 13, color: k.ink2), maxLines: 1, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 8),
                Text.rich(TextSpan(children: [
                  TextSpan(text: facts.join('  ·  '), style: body(context, 14, w: FontWeight.w500)),
                  if (verdictText != null) ...[
                    TextSpan(text: '  ·  ', style: body(context, 14)),
                    TextSpan(text: verdictText, style: body(context, 14, w: FontWeight.w600, color: k.verdict(verdict))),
                  ],
                ])),
              ]),
            ),
            const SizedBox(width: 12),
            SevStamp(s.maxSeverity, size: 40),
          ]),
        ),
        const Rule(indent: 20),
      ]),
    );
  }
}
