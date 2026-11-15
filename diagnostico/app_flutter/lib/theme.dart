import 'package:flutter/material.dart';

/// Paleta "parte de taller": papel, tinta y un solo color de aviso.
/// Claro para trabajar al sol, "noche" para cabina o taller oscuro.
@immutable
class Tinta extends ThemeExtension<Tinta> {
  final Color paper, paper2, ink, ink2, ink3, rule, accent, ok, warn, danger;
  const Tinta({
    required this.paper, required this.paper2, required this.ink, required this.ink2, required this.ink3,
    required this.rule, required this.accent, required this.ok, required this.warn, required this.danger,
  });

  static const day = Tinta(
    paper: Color(0xFFF2EEE5), paper2: Color(0xFFE8E2D4), ink: Color(0xFF1C1B19), ink2: Color(0xFF57534B),
    ink3: Color(0xFF8C877C), rule: Color(0x261C1B19), accent: Color(0xFFC2410C), ok: Color(0xFF2F6B3A),
    warn: Color(0xFFA86A12), danger: Color(0xFFB3261E),
  );
  static const night = Tinta(
    paper: Color(0xFF171614), paper2: Color(0xFF221F1B), ink: Color(0xFFEDE7DA), ink2: Color(0xFFB0A99B),
    ink3: Color(0xFF7D776B), rule: Color(0x2EEDE7DA), accent: Color(0xFFF07B3F), ok: Color(0xFF7DB886),
    warn: Color(0xFFE0A84A), danger: Color(0xFFEB6A5F),
  );

  Color severity(int s) => switch (s) { 5 => danger, 4 => accent, 3 => warn, 2 => ink2, _ => ink3 };
  Color verdict(String? v) => switch (v) { 'ok' => ok, 'sospechoso' => warn, 'manipulado' => danger, _ => ink3 };

  @override
  Tinta copyWith() => this;
  @override
  Tinta lerp(Tinta? other, double t) => t < 0.5 ? this : (other ?? this);
}

extension InkX on BuildContext {
  Tinta get ink => Theme.of(this).extension<Tinta>()!;
}

const fCond = 'BarlowCondensed';
const fMono = 'PlexMono';
const fBody = 'Barlow';

const difficultyLabels = {
  1: 'lo hace el operador',
  2: 'mecánico, sin complicación',
  3: 'mecánico con experiencia',
  4: 'especialista',
  5: 'taller oficial / software de marca',
};

ThemeData buildTheme(Tinta k, Brightness b) {
  final scheme = ColorScheme.fromSeed(seedColor: k.accent, brightness: b, primary: k.accent, surface: k.paper,
      onSurface: k.ink);
  return ThemeData(
    useMaterial3: true,
    brightness: b,
    colorScheme: scheme,
    fontFamily: fBody,
    scaffoldBackgroundColor: k.paper,
    extensions: [k],
    dividerColor: k.rule,
    splashFactory: NoSplash.splashFactory,
    highlightColor: k.rule,
    textTheme: Typography.material2021().black.apply(fontFamily: fBody, bodyColor: k.ink, displayColor: k.ink),
    appBarTheme: AppBarTheme(backgroundColor: k.paper, foregroundColor: k.ink, elevation: 0, scrolledUnderElevation: 0,
        centerTitle: false),
    inputDecorationTheme: InputDecorationTheme(
      border: UnderlineInputBorder(borderSide: BorderSide(color: k.ink2)),
      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: k.ink3)),
      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: k.accent, width: 2)),
      labelStyle: TextStyle(color: k.ink2),
      hintStyle: TextStyle(color: k.ink3),
    ),
    snackBarTheme: SnackBarThemeData(backgroundColor: k.ink, contentTextStyle: TextStyle(color: k.paper, fontFamily: fBody),
        behavior: SnackBarBehavior.floating, shape: const RoundedRectangleBorder()),
  );
}
