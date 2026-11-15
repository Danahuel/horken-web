import 'dart:math';

import 'package:flutter/material.dart';

import '../theme.dart';

TextStyle cond(BuildContext c, double size, {FontWeight w = FontWeight.w600, Color? color, double ls = 0}) =>
    TextStyle(fontFamily: fCond, fontSize: size, fontWeight: w, color: color ?? c.ink.ink, letterSpacing: ls, height: 1.1);
TextStyle mono(BuildContext c, double size, {FontWeight w = FontWeight.w400, Color? color}) =>
    TextStyle(fontFamily: fMono, fontSize: size, fontWeight: w, color: color ?? c.ink.ink, height: 1.25);
TextStyle body(BuildContext c, double size, {FontWeight w = FontWeight.w400, Color? color}) =>
    TextStyle(fontFamily: fBody, fontSize: size, fontWeight: w, color: color ?? c.ink.ink, height: 1.35);

/// Línea fina de separación, como en un formulario impreso.
class Rule extends StatelessWidget {
  final double indent;
  final bool strong;
  const Rule({super.key, this.indent = 0, this.strong = false});
  @override
  Widget build(BuildContext context) => Container(
      margin: EdgeInsets.only(left: indent),
      height: strong ? 2 : 1,
      color: strong ? context.ink.ink : context.ink.rule);
}

/// "02 ─ AVERÍAS ACTIVAS"
class SectionHeader extends StatelessWidget {
  final String number;
  final String title;
  final Widget? trailing;
  const SectionHeader(this.number, this.title, {super.key, this.trailing});
  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 28, 20, 10),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Text(number, style: mono(context, 12, color: k.accent, w: FontWeight.w500)),
        const SizedBox(width: 10),
        Expanded(child: Text(title.toUpperCase(), style: cond(context, 15, w: FontWeight.w700, ls: 1.4))),
        if (trailing != null) trailing!,
      ]),
    );
  }
}

/// Gravedad como número "sellado" en una caja.
class SevStamp extends StatelessWidget {
  final int severity;
  final double size;
  const SevStamp(this.severity, {super.key, this.size = 34});
  @override
  Widget build(BuildContext context) {
    if (severity <= 0) {
      return Container(width: size, height: size, alignment: Alignment.center,
          decoration: BoxDecoration(border: Border.all(color: context.ink.ok, width: 1.6)),
          child: Icon(Icons.check, size: size * 0.6, color: context.ink.ok));
    }
    final c = context.ink.severity(severity);
    final filled = severity >= 4;
    return Container(
      width: size, height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: filled ? c : Colors.transparent, border: Border.all(color: c, width: 1.6)),
      child: Text('$severity', style: cond(context, size * 0.62, w: FontWeight.w700,
          color: filled ? context.ink.paper : c)),
    );
  }
}

/// Dificultad como 5 barras de altura creciente (tipo cobertura).
class DifficultyBars extends StatelessWidget {
  final int level;
  final bool label;
  const DifficultyBars(this.level, {super.key, this.label = true});
  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.end, children: [
      for (var i = 1; i <= 5; i++)
        Container(width: 5, height: 5.0 + i * 2.6, margin: const EdgeInsets.only(right: 2.5),
            color: i <= level ? k.ink : k.rule),
      if (label) ...[
        const SizedBox(width: 8),
        Flexible(child: Text('$level/5 · ${difficultyLabels[level] ?? ''}', style: body(context, 13, color: k.ink2))),
      ],
    ]);
  }
}

/// Sello inclinado para el veredicto de horas/km: el único "toque a mano".
class VerdictStamp extends StatelessWidget {
  final String text;
  final Color color;
  const VerdictStamp(this.text, this.color, {super.key});
  @override
  Widget build(BuildContext context) => Transform.rotate(
        angle: -0.035,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
          decoration: BoxDecoration(border: Border.all(color: color, width: 2.2)),
          child: Text(text.toUpperCase(), style: cond(context, 22, w: FontWeight.w700, color: color, ls: 1.2)),
        ),
      );
}

/// Punto que parpadea + "en directo".
class LiveMark extends StatefulWidget {
  final String? suffix;
  const LiveMark({super.key, this.suffix});
  @override
  State<LiveMark> createState() => _LiveMarkState();
}

class _LiveMarkState extends State<LiveMark> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat(reverse: true);
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      FadeTransition(opacity: Tween(begin: 0.25, end: 1.0).animate(_c),
          child: Container(width: 7, height: 7, decoration: BoxDecoration(color: k.accent, shape: BoxShape.circle))),
      const SizedBox(width: 6),
      Text('en directo${widget.suffix ?? ''}', style: mono(context, 11, color: k.accent, w: FontWeight.w500)),
    ]);
  }
}

/// Fila etiqueta / valor de una ficha.
class KV extends StatelessWidget {
  final String k;
  final String v;
  final bool monoValue;
  final double keyWidth;
  const KV(this.k, this.v, {super.key, this.monoValue = false, this.keyWidth = 118});
  @override
  Widget build(BuildContext context) {
    final value = (v.isEmpty || v == 'null') ? '—' : v;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: keyWidth, child: Text(k, style: body(context, 13, color: context.ink.ink3))),
        Expanded(child: Text(value, style: monoValue ? mono(context, 12.5) : body(context, 14))),
      ]),
    );
  }
}

/// Barra de rango: dónde está el valor respecto a lo normal.
class RangeBar extends StatelessWidget {
  final double value, min, max;
  final double? lo, hi;  // zona normal
  final Color color;
  const RangeBar({super.key, required this.value, required this.min, required this.max, this.lo, this.hi,
      required this.color});
  @override
  Widget build(BuildContext context) => CustomPaint(
      size: const Size(double.infinity, 12),
      painter: _RangePainter(value, min, max, lo, hi, color, context.ink));
}

class _RangePainter extends CustomPainter {
  final double v, mn, mx;
  final double? lo, hi;
  final Color c;
  final Tinta k;
  _RangePainter(this.v, this.mn, this.mx, this.lo, this.hi, this.c, this.k);
  @override
  void paint(Canvas canvas, Size s) {
    double x(double val) => ((val - mn) / (mx - mn)).clamp(0.0, 1.0) * s.width;
    final y = s.height / 2;
    canvas.drawLine(Offset(0, y), Offset(s.width, y), Paint()..color = k.rule..strokeWidth = 2);
    if (lo != null || hi != null) {
      canvas.drawLine(Offset(x(lo ?? mn), y), Offset(x(hi ?? mx), y), Paint()..color = k.ink3..strokeWidth = 2);
    }
    for (var i = 0; i <= 10; i++) {
      final tx = s.width * i / 10;
      canvas.drawLine(Offset(tx, y - (i % 5 == 0 ? 4 : 2)), Offset(tx, y), Paint()..color = k.ink3..strokeWidth = 1);
    }
    final px = x(v);
    canvas.drawRect(Rect.fromCenter(center: Offset(px, y), width: 3, height: s.height), Paint()..color = c);
  }

  @override
  bool shouldRepaint(covariant _RangePainter o) => o.v != v || o.c != c;
}

/// Línea de tendencia, sin relleno.
class Trend extends StatelessWidget {
  final List<double> values;
  final Color color;
  const Trend(this.values, this.color, {super.key});
  @override
  Widget build(BuildContext context) => CustomPaint(painter: _TrendPainter(values, color), size: Size.infinite);
}

class _TrendPainter extends CustomPainter {
  final List<double> v;
  final Color color;
  _TrendPainter(this.v, this.color);
  @override
  void paint(Canvas canvas, Size size) {
    if (v.length < 2) return;
    final lo = v.reduce(min), hi = v.reduce(max);
    final span = (hi - lo).abs() < 1e-6 ? 1.0 : hi - lo;
    final path = Path();
    for (var i = 0; i < v.length; i++) {
      final x = size.width * i / (v.length - 1);
      final y = size.height - (v[i] - lo) / span * size.height;
      i == 0 ? path.moveTo(x, y) : path.lineTo(x, y);
    }
    canvas.drawPath(path, Paint()
      ..color = color
      ..strokeWidth = 1.4
      ..style = PaintingStyle.stroke);
  }

  @override
  bool shouldRepaint(covariant _TrendPainter old) => true;
}

/// Botón principal: rectangular, tinta llena.
class InkButton extends StatelessWidget {
  final String text;
  final VoidCallback? onTap;
  final bool busy;
  final bool accent;
  const InkButton(this.text, {super.key, this.onTap, this.busy = false, this.accent = true});
  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final bg = onTap == null ? k.rule : (accent ? k.accent : k.ink);
    return Material(
      color: bg,
      child: InkWell(
        onTap: busy ? null : onTap,
        child: Container(
          height: 54, alignment: Alignment.center,
          child: busy
              ? SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: k.paper))
              : Text(text.toUpperCase(), style: cond(context, 17, w: FontWeight.w700, color: k.paper, ls: 1.5)),
        ),
      ),
    );
  }
}
