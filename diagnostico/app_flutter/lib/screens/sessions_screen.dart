import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'session_screen.dart';

class SessionsScreen extends StatelessWidget {
  final SessionRepository repo;
  const SessionsScreen({super.key, required this.repo});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(children: [
          Icon(Icons.precision_manufacturing, color: kAmber),
          SizedBox(width: 10),
          Text('HORKEN', style: TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2)),
        ]),
        actions: [
          if (!repo.isDemo)
            IconButton(icon: const Icon(Icons.logout), tooltip: 'Salir', onPressed: () => FirebaseAuth.instance.signOut()),
        ],
      ),
      body: StreamBuilder<List<Session>>(
        stream: repo.sessions(),
        builder: (context, snap) {
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final list = snap.data!;
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
            children: [
              if (repo.isDemo)
                Container(
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: kAmber.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: kAmber.withValues(alpha: 0.5))),
                  child: const Text(
                      'MODO DEMOSTRACIÓN · datos del simulador de máquinas. Al configurar Firebase verás aquí las '
                      'máquinas reales que lea el portátil.',
                      style: TextStyle(fontSize: 12)),
                ),
              Text('Diagnósticos', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (list.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(32),
                  child: Text('Todavía no hay diagnósticos. Conecta el lector en el portátil para empezar.',
                      textAlign: TextAlign.center),
                ),
              for (final s in list) ...[_SessionCard(s, repo), const SizedBox(height: 10)],
            ],
          );
        },
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  final Session s;
  final SessionRepository repo;
  const _SessionCard(this.s, this.repo);

  @override
  Widget build(BuildContext context) {
    final sev = severityColors[s.maxSeverity]!;
    final t = s.tamper;
    final d = s.updatedAt;
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => SessionScreen(repo: repo, id: s.id))),
      child: Container(
        decoration: BoxDecoration(color: kCard, borderRadius: BorderRadius.circular(14),
            border: Border(left: BorderSide(color: sev, width: 5))),
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(s.title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800))),
            if (s.isLive) const LiveDot(),
          ]),
          const SizedBox(height: 2),
          Text('Nº serie ${s.machine['serial'] ?? '—'} · ${s.machine['machine_class_label'] ?? ''}',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 6, children: [
            _chip(Icons.error_outline, '${s.activeCount} activas', sev),
            _chip(Icons.history, '${s.summary['history_dtcs'] ?? 0} históricas', Colors.white54),
            _chip(Icons.timer_outlined, '${fmtNum(t['reported_hours'], decimals: 0)} h', Colors.white54),
            _chip(Icons.policy_outlined, '${t['label'] ?? ''}', verdictColor(t['verdict'] as String?)),
          ]),
          if (d != null) ...[
            const SizedBox(height: 8),
            Text('${s.operator.isNotEmpty ? '${s.operator} · ' : ''}${s.location.isNotEmpty ? '${s.location} · ' : ''}'
                '${d.day}/${d.month}/${d.year} ${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}',
                style: const TextStyle(color: Colors.white38, fontSize: 11)),
          ],
        ]),
      ),
    );
  }

  Widget _chip(IconData i, String t, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(color: c.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Icon(i, size: 14, color: c),
          const SizedBox(width: 4),
          Text(t, style: TextStyle(fontSize: 12, color: c, fontWeight: FontWeight.w600)),
        ]),
      );
}
