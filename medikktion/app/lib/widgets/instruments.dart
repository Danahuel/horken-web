import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../data/session.dart';
import '../theme.dart';

const _glide = Duration(milliseconds: 1100);

/// Interpola suavemente entre lecturas: el valor "viaja" hasta el nuevo dato
/// en lugar de saltar, como la aguja o el mercurio de un instrumento real.
class Smooth extends StatelessWidget {
  final double value;
  final Widget Function(BuildContext, double) builder;
  final Duration duration;
  const Smooth({super.key, required this.value, required this.builder, this.duration = _glide});
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(end: value), duration: duration, curve: Curves.easeOutCubic,
        builder: (c, v, _) => builder(c, v),
      );
}

/// Cifra en vivo con sus decimales y unidad.
class LiveNumber extends StatelessWidget {
  final double value;
  final int decimals;
  final String unit;
  final double size;
  final Color? color;
  final FontWeight weight;
  const LiveNumber(this.value, {super.key, this.decimals = 1, this.unit = '', this.size = 28, this.color,
      this.weight = FontWeight.w300});
  @override
  Widget build(BuildContext context) => Smooth(
        value: value,
        builder: (c, v) => Text.rich(
          TextSpan(children: [
            TextSpan(text: fmtNum(v, decimals: decimals), style: num_(c, size, w: weight, color: color)),
            if (unit.isNotEmpty) TextSpan(text: ' $unit', style: tx(c, size * 0.42, color: c.p.text3, w: FontWeight.w500)),
          ]),
          maxLines: 1,
        ),
      );
}

/// Panel base: superficie, borde fino y radio contenido.
class Panel extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final Color? border;
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(18), this.border});
  @override
  Widget build(BuildContext context) => Container(
        padding: padding,
        decoration: BoxDecoration(
          color: context.p.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: border ?? context.p.line),
        ),
        child: child,
      );
}

class SectionLabel extends StatelessWidget {
  final String text;
  final Widget? trailing;
  final EdgeInsets padding;
  const SectionLabel(this.text, {super.key, this.trailing, this.padding = const EdgeInsets.fromLTRB(4, 26, 4, 12)});
  @override
  Widget build(BuildContext context) => Padding(
        padding: padding,
        child: Row(children: [
          Container(width: 14, height: 1, color: context.p.gold),
          const SizedBox(width: 10),
          Expanded(child: Text(text.toUpperCase(), style: label(context, color: context.p.gold))),
          if (trailing != null) trailing!,
        ]),
      );
}

class LivePulse extends StatefulWidget {
  final String text;
  const LivePulse({super.key, this.text = 'EN DIRECTO'});
  @override
  State<LivePulse> createState() => _LivePulseState();
}

class _LivePulseState extends State<LivePulse> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1600))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final g = context.p.gold;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(
        width: 14, height: 14,
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, _) => CustomPaint(painter: _PulsePainter(_c.value, g)),
        ),
      ),
      const SizedBox(width: 6),
      Text(widget.text, style: label(context, color: g, size: 10)),
    ]);
  }
}

class _PulsePainter extends CustomPainter {
  final double t;
  final Color c;
  _PulsePainter(this.t, this.c);
  @override
  void paint(Canvas canvas, Size s) {
    final o = s.center(Offset.zero);
    canvas.drawCircle(o, 2 + t * 5, Paint()..color = c.withValues(alpha: (1 - t) * 0.45));
    canvas.drawCircle(o, 3, Paint()..color = c);
  }

  @override
  bool shouldRepaint(covariant _PulsePainter o) => o.t != t;
}

// ═════════════════════════════════════════════════════════════ ÍNDICE DE ESTADO
/// Esfera tipo reloj: 60 marcas, arco de progreso y la cifra en el centro.
class HealthDial extends StatelessWidget {
  final int score;
  final String caption;
  final double size;
  const HealthDial({super.key, required this.score, required this.caption, this.size = 176});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final color = p.health(score);
    return SizedBox(
      width: size, height: size,
      child: Smooth(
        value: score.toDouble(),
        duration: const Duration(milliseconds: 1400),
        builder: (c, v) => CustomPaint(
          painter: _HealthPainter(v / 100, color, p),
          child: Center(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(v.round().toString(), style: num_(c, size * (caption.isEmpty ? 0.27 : 0.28), w: FontWeight.w200)),
              if (caption.isNotEmpty) ...[
                const SizedBox(height: 4),
                SizedBox(width: size * 0.6, child: Text(caption.toUpperCase(), style: label(c, color: color, size: 9),
                    textAlign: TextAlign.center, maxLines: 2)),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

class _HealthPainter extends CustomPainter {
  final double f;
  final Color color;
  final Paleta p;
  _HealthPainter(this.f, this.color, this.p);
  @override
  void paint(Canvas canvas, Size s) {
    final c = s.center(Offset.zero);
    final r = s.shortestSide / 2;
    const start = math.pi * 0.75, sweep = math.pi * 1.5;
    for (var i = 0; i <= 60; i++) {
      final a = start + sweep * i / 60;
      final major = i % 10 == 0;
      final on = i / 60 <= f;
      final r1 = r - (major ? r * 0.13 : r * 0.08);
      canvas.drawLine(c + Offset(math.cos(a), math.sin(a)) * r1, c + Offset(math.cos(a), math.sin(a)) * (r - 2),
          Paint()
            ..color = on ? color.withValues(alpha: major ? 1 : 0.75) : p.line2
            ..strokeWidth = major ? 1.6 : 1);
    }
    final rect = Rect.fromCircle(center: c, radius: r * 0.8);
    canvas.drawArc(rect, start, sweep, false, Paint()
      ..color = p.line
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2);
    canvas.drawArc(rect, start, sweep * f, false, Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.4);
  }

  @override
  bool shouldRepaint(covariant _HealthPainter o) => o.f != f || o.color != color;
}

// ═════════════════════════════════════════════════════════════ TERMÓMETRO
class Thermometer extends StatelessWidget {
  final Measure m;
  final double value; // ya convertido
  final double height;
  const Thermometer({super.key, required this.m, required this.value, this.height = 210});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final alert = m.isHigh(value) || m.isLow(value);
    final color = alert ? p.danger : p.gold;
    return Panel(
      padding: const EdgeInsets.fromLTRB(14, 16, 14, 14),
      border: alert ? p.danger.withValues(alpha: 0.5) : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(height: 26, child: Text(m.label.toUpperCase(), style: label(context, size: 9).copyWith(letterSpacing: 1.2),
            maxLines: 2)),
        const SizedBox(height: 8),
        FittedBox(
          fit: BoxFit.scaleDown, alignment: Alignment.centerLeft,
          child: LiveNumber(value, decimals: m.decimals, unit: m.unit, size: 26, color: alert ? p.danger : p.text),
        ),
        const SizedBox(height: 14),
        SizedBox(
          height: height,
          child: Smooth(
            value: value,
            builder: (c, v) => CustomPaint(size: Size.infinite, painter: _ThermoPainter(m, v, color, p)),
          ),
        ),
        const SizedBox(height: 8),
        Text(m.hi != null ? 'MÁX. ${fmtNum(m.hi, decimals: 0)} ${m.unit}' : '', style: label(context, size: 8.5)),
      ]),
    );
  }
}

class _ThermoPainter extends CustomPainter {
  final Measure m;
  final double v;
  final Color color;
  final Paleta p;
  _ThermoPainter(this.m, this.v, this.color, this.p);

  @override
  void paint(Canvas canvas, Size s) {
    const tubeW = 9.0, bulbR = 11.0;
    final cx = s.width * 0.62;
    final top = 6.0, bottom = s.height - bulbR * 2 - 2;
    double y(double val) => bottom - ((val - m.min) / (m.max - m.min)).clamp(0.0, 1.0) * (bottom - top);

    // Escala: marca cada 2 °C, mayor cada 10 °C, con cifras a la izquierda
    final tp = TextPainter(textDirection: TextDirection.ltr);
    for (var t = m.min; t <= m.max + 0.01; t += 2) {
      final major = (t - m.min) % 10 == 0;
      final yy = y(t);
      canvas.drawLine(Offset(cx - tubeW / 2 - (major ? 12 : 6), yy), Offset(cx - tubeW / 2 - 3, yy),
          Paint()
            ..color = major ? p.text3 : p.line2
            ..strokeWidth = 1);
      if (major) {
        tp.text = TextSpan(text: t.toStringAsFixed(0),
            style: TextStyle(fontFamily: fSans, fontSize: 9, color: p.text3, fontFeatures: tabular));
        tp.layout();
        tp.paint(canvas, Offset(cx - tubeW / 2 - 16 - tp.width, yy - tp.height / 2));
      }
    }
    // Zona normal a la derecha del tubo
    if (m.lo != null || m.hi != null) {
      canvas.drawLine(Offset(cx + tubeW / 2 + 5, y(m.hi ?? m.max)), Offset(cx + tubeW / 2 + 5, y(m.lo ?? m.min)),
          Paint()
            ..color = p.ok.withValues(alpha: 0.7)
            ..strokeWidth = 2);
      if (m.hi != null) {
        canvas.drawLine(Offset(cx + tubeW / 2 + 5, y(m.max)), Offset(cx + tubeW / 2 + 5, y(m.hi!)),
            Paint()
              ..color = p.danger.withValues(alpha: 0.75)
              ..strokeWidth = 2);
      }
    }
    // Tubo y bulbo
    final tube = RRect.fromRectAndRadius(Rect.fromLTRB(cx - tubeW / 2, top - 4, cx + tubeW / 2, bottom + 6),
        const Radius.circular(tubeW / 2));
    final bulb = Offset(cx, s.height - bulbR - 1);
    canvas.drawRRect(tube, Paint()..color = p.surface2);
    canvas.drawCircle(bulb, bulbR, Paint()..color = p.surface2);
    canvas.drawRRect(tube, Paint()
      ..color = p.line2
      ..style = PaintingStyle.stroke);
    // Columna
    final colTop = y(v);
    final shader = LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter,
        colors: [color.withValues(alpha: 0.85), color]).createShader(Rect.fromLTRB(0, colTop, s.width, s.height));
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTRB(cx - tubeW / 2 + 2.2, colTop, cx + tubeW / 2 - 2.2, bottom + 8),
            const Radius.circular(3)),
        Paint()..shader = shader);
    canvas.drawCircle(bulb, bulbR - 2.6, Paint()..color = color);
    // Brillo del cristal
    canvas.drawLine(Offset(cx - tubeW / 2 + 1.6, top + 2), Offset(cx - tubeW / 2 + 1.6, bottom),
        Paint()
          ..color = Colors.white.withValues(alpha: p.dark ? 0.06 : 0.5)
          ..strokeWidth = 1);
    // Menisco
    canvas.drawLine(Offset(cx + tubeW / 2 + 1, colTop), Offset(cx + tubeW / 2 + 10, colTop),
        Paint()
          ..color = color
          ..strokeWidth = 1.2);
  }

  @override
  bool shouldRepaint(covariant _ThermoPainter o) => o.v != v || o.color != color;
}

// ═════════════════════════════════════════════════════════════ ESFERA CON AGUJA
class Dial extends StatelessWidget {
  final Measure m;
  final double value;
  final double majorStep;
  final String Function(double)? tickLabel;
  const Dial({super.key, required this.m, required this.value, required this.majorStep, this.tickLabel});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final alert = m.isHigh(value) || m.isLow(value);
    return Panel(
      padding: const EdgeInsets.fromLTRB(12, 14, 12, 12),
      border: alert ? p.danger.withValues(alpha: 0.5) : null,
      child: Column(children: [
        Align(alignment: Alignment.centerLeft, child: Text(m.label.toUpperCase(), style: label(context, size: 9.5))),
        const SizedBox(height: 6),
        AspectRatio(
          aspectRatio: 1.0,
          child: Smooth(
            value: value,
            builder: (c, v) => CustomPaint(
              painter: _DialPainter(m, v, majorStep, p, tickLabel),
              child: Align(
                alignment: const Alignment(0, 1),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  Text(fmtNum(v, decimals: m.decimals), style: num_(c, 24, color: alert ? p.danger : p.text)),
                  const SizedBox(height: 3),
                  Text(m.unit.toUpperCase(), style: label(c, size: 9)),
                ]),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

class _DialPainter extends CustomPainter {
  final Measure m;
  final double v, step;
  final Paleta p;
  final String Function(double)? lbl;
  _DialPainter(this.m, this.v, this.step, this.p, this.lbl);

  @override
  void paint(Canvas canvas, Size s) {
    final c = Offset(s.width / 2, s.height * 0.42);
    final r = math.min(s.width / 2, s.height * 0.42) - 4;
    const start = math.pi * 0.75, sweep = math.pi * 1.5;
    double ang(double val) => start + sweep * ((val - m.min) / (m.max - m.min)).clamp(0.0, 1.0);
    Offset at(double a, double rr) => c + Offset(math.cos(a), math.sin(a)) * rr;

    // Zonas: normal (verde tenue) y roja
    final arc = Rect.fromCircle(center: c, radius: r - 3);
    final band = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    if (m.lo != null) {
      canvas.drawArc(arc, ang(m.min), ang(m.lo!) - ang(m.min), false, band..color = p.danger.withValues(alpha: 0.7));
    }
    if (m.hi != null) {
      canvas.drawArc(arc, ang(m.hi!), ang(m.max) - ang(m.hi!), false, band..color = p.danger.withValues(alpha: 0.7));
    }
    canvas.drawArc(arc, ang(m.lo ?? m.min), ang(m.hi ?? m.max) - ang(m.lo ?? m.min), false,
        band..color = p.ok.withValues(alpha: 0.35));

    // Marcas y cifras
    final tp = TextPainter(textDirection: TextDirection.ltr);
    final minor = step / 5;
    for (var t = m.min; t <= m.max + 1e-6; t += minor) {
      final major = ((t - m.min) / step - ((t - m.min) / step).round()).abs() < 1e-6;
      final a = ang(t);
      canvas.drawLine(at(a, r - (major ? 16 : 10)), at(a, r - 7),
          Paint()
            ..color = major ? p.text2 : p.line2
            ..strokeWidth = major ? 1.4 : 1);
      if (major) {
        tp.text = TextSpan(text: lbl != null ? lbl!(t) : fmtNum(t, decimals: 0),
            style: TextStyle(fontFamily: fSans, fontSize: 9.5, color: p.text3, fontFeatures: tabular));
        tp.layout();
        final o = at(a, r - 26);
        tp.paint(canvas, o - Offset(tp.width / 2, tp.height / 2));
      }
    }
    // Aguja
    final a = ang(v);
    final needle = Paint()
      ..color = p.gold
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(at(a + math.pi, 8), at(a, r - 12), needle);
    canvas.drawCircle(c, 5, Paint()..color = p.surface2);
    canvas.drawCircle(c, 5, Paint()
      ..color = p.gold
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6);
  }

  @override
  bool shouldRepaint(covariant _DialPainter o) => o.v != v;
}

// ═════════════════════════════════════════════════════════════ LECTURA COMPACTA
class Readout extends StatelessWidget {
  final Measure m;
  final double value;
  const Readout({super.key, required this.m, required this.value});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final alert = m.isHigh(value) || m.isLow(value);
    final f = ((value - m.min) / (m.max - m.min)).clamp(0.0, 1.0);
    return Panel(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      border: alert ? p.danger.withValues(alpha: 0.5) : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(m.label.toUpperCase(), style: label(context, size: 9.5), maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 8),
        FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft,
            child: LiveNumber(value, decimals: m.decimals, unit: m.unit, size: 22, color: alert ? p.danger : p.text)),
        const SizedBox(height: 10),
        Smooth(
          value: f,
          builder: (c, v) => LayoutBuilder(builder: (c, box) => Stack(children: [
                Container(height: 2, color: p.line2),
                Container(height: 2, width: box.maxWidth * v, color: alert ? p.danger : p.gold),
              ])),
        ),
      ]),
    );
  }
}

// ═════════════════════════════════════════════════════════════ TENDENCIA
class TrendChart extends StatelessWidget {
  final Measure m;
  final List<double> t, v; // v ya convertido
  final double height;
  const TrendChart({super.key, required this.m, required this.t, required this.v, this.height = 130});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    if (v.length < 2) return const SizedBox();
    final lo = v.reduce(math.min), hi = v.reduce(math.max);
    final avg = v.reduce((a, b) => a + b) / v.length;
    final minutes = ((t.last - t.first) / 60).round();
    return Panel(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Expanded(child: Text(m.label.toUpperCase(), style: label(context, size: 9.5))),
          _stat(context, 'MÍN', lo),
          _stat(context, 'MEDIA', avg),
          _stat(context, 'MÁX', hi),
        ]),
        const SizedBox(height: 12),
        SizedBox(height: height, child: CustomPaint(size: Size.infinite, painter: _TrendPainter(m, t, v, p))),
        const SizedBox(height: 6),
        Row(children: [
          Text('−$minutes min', style: tx(context, 10, color: p.text3)),
          const Spacer(),
          Text('−${(minutes / 2).round()} min', style: tx(context, 10, color: p.text3)),
          const Spacer(),
          Text('ahora', style: tx(context, 10, color: p.text3)),
        ]),
      ]),
    );
  }

  Widget _stat(BuildContext c, String k, double val) => Padding(
        padding: const EdgeInsets.only(left: 14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
          Text(k, style: label(c, size: 8.5)),
          const SizedBox(height: 2),
          Text(fmtNum(val, decimals: m.decimals), style: tx(c, 12.5, w: FontWeight.w500)),
        ]),
      );
}

class _TrendPainter extends CustomPainter {
  final Measure m;
  final List<double> t, v;
  final Paleta p;
  _TrendPainter(this.m, this.t, this.v, this.p);
  @override
  void paint(Canvas canvas, Size s) {
    var lo = v.reduce(math.min), hi = v.reduce(math.max);
    final pad = math.max((hi - lo) * 0.18, m.decimals >= 2 ? 0.05 : 1.0);
    lo -= pad;
    hi += pad;
    double x(double tt) => (tt - t.first) / math.max(1e-6, t.last - t.first) * s.width;
    double y(double vv) => s.height - (vv - lo) / (hi - lo) * s.height;

    // Rejilla y valores a la derecha
    final tp = TextPainter(textDirection: TextDirection.ltr);
    for (var i = 0; i <= 3; i++) {
      final yy = s.height * i / 3;
      canvas.drawLine(Offset(0, yy), Offset(s.width, yy), Paint()
        ..color = p.line
        ..strokeWidth = 1);
      final val = hi - (hi - lo) * i / 3;
      tp.text = TextSpan(text: fmtNum(val, decimals: m.decimals >= 2 ? 1 : 0),
          style: TextStyle(fontFamily: fSans, fontSize: 9, color: p.text3, fontFeatures: tabular));
      tp.layout();
      tp.paint(canvas, Offset(s.width - tp.width, yy + (i == 3 ? -tp.height - 2 : 2)));
    }
    // Límite de alarma si cae dentro del rango visible
    for (final lim in [m.hi, m.lo]) {
      if (lim != null && lim > lo && lim < hi) {
        final yy = y(lim);
        for (var xx = 0.0; xx < s.width; xx += 6) {
          canvas.drawLine(Offset(xx, yy), Offset(xx + 3, yy), Paint()
            ..color = p.danger.withValues(alpha: 0.7)
            ..strokeWidth = 1);
        }
      }
    }
    final path = Path();
    for (var i = 0; i < v.length; i++) {
      i == 0 ? path.moveTo(x(t[i]), y(v[i])) : path.lineTo(x(t[i]), y(v[i]));
    }
    final fill = Path.from(path)
      ..lineTo(x(t.last), s.height)
      ..lineTo(x(t.first), s.height)
      ..close();
    canvas.drawPath(fill, Paint()
      ..shader = LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter,
          colors: [p.gold.withValues(alpha: 0.20), p.gold.withValues(alpha: 0.0)]).createShader(Offset.zero & s));
    canvas.drawPath(path, Paint()
      ..color = p.gold
      ..strokeWidth = 1.6
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round);
    canvas.drawCircle(Offset(x(t.last), y(v.last)), 3.2, Paint()..color = p.gold);
    canvas.drawCircle(Offset(x(t.last), y(v.last)), 6, Paint()..color = p.gold.withValues(alpha: 0.2));
  }

  @override
  bool shouldRepaint(covariant _TrendPainter o) => true;
}

// ═════════════════════════════════════════════════════════════ PEQUEÑOS
class SeverityTag extends StatelessWidget {
  final int severity;
  const SeverityTag(this.severity, {super.key});
  @override
  Widget build(BuildContext context) {
    final c = context.p.severity(severity);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 1; i <= 5; i++)
        Container(width: 4, height: 10, margin: const EdgeInsets.only(right: 2),
            decoration: BoxDecoration(color: i <= severity ? c : context.p.line2, borderRadius: BorderRadius.circular(1))),
      const SizedBox(width: 7),
      Text((severityLabels[severity] ?? '').toUpperCase(), style: label(context, color: c, size: 9.5)),
    ]);
  }
}

class DifficultyScale extends StatelessWidget {
  final int level;
  const DifficultyScale(this.level, {super.key});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        for (var i = 1; i <= 5; i++)
          Expanded(
            child: Container(
              height: 4, margin: EdgeInsets.only(right: i < 5 ? 4 : 0),
              decoration: BoxDecoration(
                  color: i <= level ? p.gold.withValues(alpha: 0.45 + i * 0.11) : p.line2,
                  borderRadius: BorderRadius.circular(2)),
            ),
          ),
      ]),
      const SizedBox(height: 8),
      Text('$level de 5 · ${difficultyLabels[level] ?? ''}', style: tx(context, 13, color: p.text2)),
    ]);
  }
}

/// Barras horizontales: horas que guarda cada centralita.
class HoursBars extends StatelessWidget {
  final List<(String, double)> items;
  final double? estimated;
  /// true = lista en el tiempo: solo es sospechoso tener MENOS horas que una lectura anterior.
  final bool chronological;
  const HoursBars({super.key, required this.items, this.estimated, this.chronological = false});

  bool _bad(int i, double hi) {
    final h = items[i].$2;
    if (chronological) {
      final before = items.take(i).map((e) => e.$2);
      return before.isNotEmpty && h < before.reduce(math.max) - 1;
    }
    return (hi - h) > math.max(20, hi * 0.02);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final maxV = [...items.map((e) => e.$2), estimated ?? 0].reduce(math.max);
    final hi = items.map((e) => e.$2).reduce(math.max);
    return Column(children: [
      for (final (i, (name, h)) in items.indexed)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text(name, style: tx(context, 12.5, color: p.text2), maxLines: 1, overflow: TextOverflow.ellipsis)),
              Text('${fmtNum(h)} h', style: tx(context, 12.5, w: FontWeight.w500, color: _bad(i, hi) ? p.danger : p.text)),
            ]),
            const SizedBox(height: 6),
            Smooth(
              value: h / maxV,
              duration: const Duration(milliseconds: 1400),
              builder: (c, f) => LayoutBuilder(builder: (c, box) => Stack(children: [
                    Container(height: 3, decoration: BoxDecoration(color: p.line, borderRadius: BorderRadius.circular(2))),
                    Container(height: 3, width: box.maxWidth * f, decoration: BoxDecoration(
                        color: _bad(i, hi) ? p.danger : p.gold,
                        borderRadius: BorderRadius.circular(2))),
                  ])),
            ),
          ]),
        ),
    ]);
  }
}

class GoldButton extends StatelessWidget {
  final String text;
  final VoidCallback? onTap;
  final bool busy;
  final bool outline;
  const GoldButton(this.text, {super.key, this.onTap, this.busy = false, this.outline = false});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final enabled = onTap != null && !busy;
    return Material(
      color: outline ? Colors.transparent : (enabled ? p.gold : p.line2),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12),
          side: outline ? BorderSide(color: p.gold.withValues(alpha: 0.6)) : BorderSide.none),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: enabled ? onTap : null,
        child: SizedBox(
          height: 54,
          child: Center(
            child: busy
                ? SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 1.6,
                    color: outline ? p.gold : p.bg))
                : Text(text.toUpperCase(), style: label(context, size: 11.5,
                    color: outline ? p.gold : (enabled ? const Color(0xFF15120C) : p.text3))),
          ),
        ),
      ),
    );
  }
}
