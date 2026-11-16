import 'dart:async';

import 'package:flutter/material.dart';

import '../data/session.dart';
import '../theme.dart';
import 'instruments.dart';

/// Pasado este tiempo sin datos de una sesión "en directo", se considera que
/// el portátil ha perdido la conexión (sigue leyendo y guardando en local).
const staleAfter = Duration(seconds: 20);

bool isStale(Session s) {
  final u = s.updatedAt;
  return s.isLive && u != null && DateTime.now().difference(u) > staleAfter;
}

/// Se redibuja solo cada pocos segundos para detectar la falta de señal
/// aunque no llegue ningún dato nuevo.
abstract class _Ticking<T extends StatefulWidget> extends State<T> {
  Timer? _t;
  @override
  void initState() {
    super.initState();
    _t = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _t?.cancel();
    super.dispose();
  }
}

/// "EN DIRECTO", "SIN SEÑAL · 10:42" o la fecha de la última lectura.
class LinkStatus extends StatefulWidget {
  final Session s;
  const LinkStatus(this.s, {super.key});
  @override
  State<LinkStatus> createState() => _LinkStatusState();
}

class _LinkStatusState extends _Ticking<LinkStatus> {
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final s = widget.s;
    if (!s.isLive) return Text(whenText(s.updatedAt), style: tx(context, 11, color: p.text3));
    if (isStale(s)) {
      return Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.wifi_off_rounded, size: 13, color: p.warn),
        const SizedBox(width: 6),
        Text('SIN SEÑAL · ${hhmm(s.updatedAt!)}', style: label(context, color: p.warn, size: 10)),
      ]);
    }
    return const LivePulse();
  }
}

/// Aviso en la pestaña de medidas: sin señal ahora, o recuperada hace poco.
class LinkNotice extends StatefulWidget {
  final Session s;
  const LinkNotice(this.s, {super.key});
  @override
  State<LinkNotice> createState() => _LinkNoticeState();
}

class _LinkNoticeState extends _Ticking<LinkNotice> {
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final s = widget.s;
    if (isStale(s)) {
      final mins = DateTime.now().difference(s.updatedAt!).inMinutes;
      return _box(context, Icons.wifi_off_rounded, p.warn, 'Sin señal del equipo de lectura',
          'Último dato a las ${hhmm(s.updatedAt!)}${mins > 0 ? ' (hace $mins min)' : ''}. El portátil sigue leyendo y '
          'guardando; los datos aparecerán aquí en cuanto recupere la conexión.');
    }
    final c = (s.raw['connection'] as Map?) ?? const {};
    final outage = asNum(c['last_outage_s']);
    final at = DateTime.tryParse('${c['recovered_at'] ?? ''}')?.toLocal();
    if (outage != null && at != null && DateTime.now().difference(at) < const Duration(minutes: 10)) {
      final d = Duration(seconds: outage.round());
      return _box(context, Icons.cloud_done_outlined, p.ok, 'Conexión recuperada',
          'El equipo estuvo ${d.inMinutes > 0 ? '${d.inMinutes} min' : '${d.inSeconds} s'} sin conexión. '
          'Las mediciones de ese intervalo se han completado.');
    }
    return const SizedBox.shrink();
  }

  Widget _box(BuildContext c, IconData i, Color color, String title, String text) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: Panel(
          border: color.withValues(alpha: 0.45),
          padding: const EdgeInsets.all(16),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(i, color: color, size: 20),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: tx(c, 14, w: FontWeight.w500, color: color)),
              const SizedBox(height: 4),
              Text(text, style: tx(c, 12.5, color: c.p.text2, h: 1.5)),
            ])),
          ]),
        ),
      );
}
