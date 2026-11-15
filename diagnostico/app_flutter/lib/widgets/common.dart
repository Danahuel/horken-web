import 'dart:math';

import 'package:flutter/material.dart';

import '../theme.dart';

class SectionCard extends StatelessWidget {
  final String? title;
  final IconData? icon;
  final Widget child;
  final Color? accent;
  final EdgeInsets padding;
  const SectionCard({super.key, this.title, this.icon, required this.child, this.accent,
      this.padding = const EdgeInsets.all(14)});

  @override
  Widget build(BuildContext context) {
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: (accent ?? Colors.white).withValues(alpha: accent == null ? 0.06 : 0.6)),
      ),
      child: Padding(
        padding: padding,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (title != null) ...[
            Row(children: [
              if (icon != null) Icon(icon, size: 18, color: accent ?? kAmber),
              if (icon != null) const SizedBox(width: 8),
              Expanded(
                child: Text(title!.toUpperCase(),
                    style: TextStyle(
                        fontSize: 12, letterSpacing: 1.1, fontWeight: FontWeight.w700, color: accent ?? kAmber)),
              ),
            ]),
            const SizedBox(height: 10),
          ],
          child,
        ]),
      ),
    );
  }
}

class SeverityBadge extends StatelessWidget {
  final int severity;
  final bool compact;
  const SeverityBadge(this.severity, {super.key, this.compact = false});

  @override
  Widget build(BuildContext context) {
    final c = severityColors[severity] ?? Colors.grey;
    return Container(
      padding: EdgeInsets.symmetric(horizontal: compact ? 6 : 9, vertical: 3),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(6),
          border: Border.all(color: c)),
      child: Text(compact ? '$severity' : '$severity/5 ${severityLabels[severity] ?? ''}',
          style: TextStyle(color: c, fontWeight: FontWeight.w800, fontSize: 12)),
    );
  }
}

class DifficultyDots extends StatelessWidget {
  final int level;
  final bool showLabel;
  const DifficultyDots(this.level, {super.key, this.showLabel = true});

  @override
  Widget build(BuildContext context) {
    final c = severityColors[level] ?? kAmber;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 1; i <= 5; i++)
        Container(
          width: 14, height: 14, margin: const EdgeInsets.only(right: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: i <= level ? c : Colors.transparent,
            border: Border.all(color: i <= level ? c : Colors.white24, width: 1.5),
          ),
        ),
      if (showLabel) ...[
        const SizedBox(width: 6),
        Flexible(child: Text('$level/5 · ${difficultyLabels[level] ?? ''}',
            style: const TextStyle(fontSize: 12, color: Colors.white70))),
      ],
    ]);
  }
}

class StatTile extends StatelessWidget {
  final String label;
  final String value;
  final Color? color;
  final IconData icon;
  const StatTile({super.key, required this.label, required this.value, required this.icon, this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: kCard, borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white10)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 18, color: color ?? Colors.white54),
        const SizedBox(height: 6),
        FittedBox(child: Text(value, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color))),
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.white60), maxLines: 2),
      ]),
    );
  }
}

class LiveDot extends StatefulWidget {
  const LiveDot({super.key});
  @override
  State<LiveDot> createState() => _LiveDotState();
}

class _LiveDotState extends State<LiveDot> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(
        opacity: Tween(begin: 0.3, end: 1.0).animate(_c),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(color: Colors.red.shade700, borderRadius: BorderRadius.circular(20)),
          child: const Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.circle, size: 8, color: Colors.white),
            SizedBox(width: 4),
            Text('EN VIVO', style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: Colors.white)),
          ]),
        ),
      );
}

class Sparkline extends StatelessWidget {
  final List<double> values;
  final Color color;
  const Sparkline(this.values, {super.key, this.color = kAmber});
  @override
  Widget build(BuildContext context) => CustomPaint(painter: _SparkPainter(values, color), size: Size.infinite);
}

class _SparkPainter extends CustomPainter {
  final List<double> v;
  final Color color;
  _SparkPainter(this.v, this.color);

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
    final fill = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(fill, Paint()..color = color.withValues(alpha: 0.12));
    canvas.drawPath(path, Paint()
      ..color = color
      ..strokeWidth = 2
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(covariant _SparkPainter old) => true;
}
