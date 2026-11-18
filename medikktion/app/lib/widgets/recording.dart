import 'package:flutter/material.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import 'instruments.dart';
import 'status.dart';

String _size(num mb) => mb < 1 ? '${fmtNum(mb * 1024, decimals: 0)} KB' : '${fmtNum(mb, decimals: 1)} MB';

/// Indicador "● REC 2,4 MB" para la cabecera.
class RecChip extends StatefulWidget {
  final Session s;
  const RecChip(this.s, {super.key});
  @override
  State<RecChip> createState() => _RecChipState();
}

class _RecChipState extends State<RecChip> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      FadeTransition(
        opacity: Tween(begin: 0.35, end: 1.0).animate(_c),
        child: Container(width: 7, height: 7, decoration: BoxDecoration(color: p.danger, shape: BoxShape.circle)),
      ),
      const SizedBox(width: 6),
      Text('REC ${_size(asNum(widget.s.recording['mb']) ?? 0)}', style: label(context, color: p.danger, size: 10)),
    ]);
  }
}

/// Panel para activar la grabación de tramas desde el móvil.
class RecordingPanel extends StatefulWidget {
  final Session s;
  final SessionRepository repo;
  const RecordingPanel({super.key, required this.s, required this.repo});
  @override
  State<RecordingPanel> createState() => _RecordingPanelState();
}

class _RecordingPanelState extends State<RecordingPanel> {
  bool _busy = false;

  Future<void> _toggle(bool v) async {
    setState(() => _busy = true);
    await widget.repo.requestRecording(widget.s.id, v);
    if (!mounted) return;
    setState(() => _busy = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(v
        ? 'Grabación solicitada al equipo de lectura.'
        : 'Grabación detenida. El archivo queda guardado en el portátil.')));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final s = widget.s;
    final r = s.recording;
    final on = s.isRecording;
    final canControl = s.isLive && !isStale(s);
    final waiting = _busy || s.recordRequested;
    final since = DateTime.tryParse('${r['since'] ?? ''}')?.toLocal();
    return Panel(
      border: on ? p.danger.withValues(alpha: 0.45) : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('GRABACIÓN DE DIAGNÓSTICO', style: label(context, size: 9.5, color: on ? p.danger : p.text3)),
            const SizedBox(height: 8),
            Text(on ? 'Grabando todas las tramas' : 'Grabar tramas CAN', style: tx(context, 16, w: FontWeight.w400)),
          ])),
          if (waiting)
            const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 1.4))
          else
            Switch(
              value: on,
              onChanged: canControl ? _toggle : null,
              activeThumbColor: p.bg,
              activeTrackColor: p.danger,
              inactiveThumbColor: p.text3,
              inactiveTrackColor: p.surface2,
              trackOutlineColor: WidgetStateProperty.all(p.line2),
            ),
        ]),
        const SizedBox(height: 10),
        if (on || r['file'] != null) ...[
          _row(context, 'Archivo', '${r['file'] ?? '—'}', mono_: true),
          _row(context, 'Tramas', fmtNum(r['frames'], decimals: 0)),
          _row(context, 'Tamaño', _size(asNum(r['mb']) ?? 0)),
          if (since != null) _row(context, 'Desde', '${hhmm(since)} · ${whenText(since).split(',').first}'),
          const SizedBox(height: 10),
        ],
        Text(
          !canControl && !on
              ? 'Disponible mientras el equipo de lectura está conectado a la máquina.'
              : 'Guarda en el portátil todo lo que transmiten las centralitas (formato BLF, unos 5–10 MB por hora). '
                  'Permite reproducir la máquina más tarde para analizar un fallo con detalle.',
          style: tx(context, 12.5, color: p.text3, h: 1.5),
        ),
      ]),
    );
  }

  Widget _row(BuildContext c, String k, String v, {bool mono_ = false}) => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Row(children: [
          SizedBox(width: 90, child: Text(k, style: tx(c, 12, color: c.p.text3))),
          Expanded(child: Text(v, style: mono_ ? mono(c, 11.5, color: c.p.text2) : tx(c, 13))),
        ]),
      );
}
