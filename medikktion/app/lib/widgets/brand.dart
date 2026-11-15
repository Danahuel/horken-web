import 'package:flutter/material.dart';

import '../theme.dart';

/// Logotipo: monograma en rombo + MEDIKKTION en versalitas espaciadas.
class Wordmark extends StatelessWidget {
  final double size;
  final bool tagline;
  const Wordmark({super.key, this.size = 15, this.tagline = false});
  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
      Row(mainAxisSize: MainAxisSize.min, children: [
        Monogram(size: size * 1.7),
        SizedBox(width: size * 0.8),
        Text('MEDIKKTION', style: TextStyle(fontFamily: fSans, fontSize: size, fontWeight: FontWeight.w300,
            letterSpacing: size * 0.42, color: p.text)),
      ]),
      if (tagline) ...[
        SizedBox(height: size * 0.9),
        Text('DIAGNÓSTICO DE MAQUINARIA PESADA', style: label(context, size: size * 0.62)),
      ],
    ]);
  }
}

class Monogram extends StatelessWidget {
  final double size;
  const Monogram({super.key, this.size = 26});
  @override
  Widget build(BuildContext context) => SizedBox(
      width: size, height: size, child: CustomPaint(painter: _MonoPainter(context.p.gold)));
}

class _MonoPainter extends CustomPainter {
  final Color c;
  _MonoPainter(this.c);
  @override
  void paint(Canvas canvas, Size s) {
    final w = s.width, h = s.height;
    final stroke = Paint()
      ..color = c
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.045
      ..strokeJoin = StrokeJoin.miter;
    // rombo exterior
    canvas.drawPath(Path()
      ..moveTo(w / 2, 0)
      ..lineTo(w, h / 2)
      ..lineTo(w / 2, h)
      ..lineTo(0, h / 2)
      ..close(), stroke);
    // M interior
    final m = Path()
      ..moveTo(w * 0.3, h * 0.64)
      ..lineTo(w * 0.3, h * 0.38)
      ..lineTo(w * 0.5, h * 0.56)
      ..lineTo(w * 0.7, h * 0.38)
      ..lineTo(w * 0.7, h * 0.64);
    canvas.drawPath(m, stroke..strokeWidth = w * 0.06);
  }

  @override
  bool shouldRepaint(covariant _MonoPainter o) => o.c != c;
}
