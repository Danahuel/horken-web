import 'package:flutter/material.dart';

/// Paleta Medikktion.
///  · Grafito (oscuro, por defecto): negro grafito, líneas finas y oro champán.
///  · Porcelana (claro): para trabajar a pleno sol.
@immutable
class Paleta extends ThemeExtension<Paleta> {
  final Color bg, surface, surface2, line, line2, text, text2, text3, gold, goldDim, ok, warn, danger, info;
  final bool dark;
  const Paleta({
    required this.bg, required this.surface, required this.surface2, required this.line, required this.line2,
    required this.text, required this.text2, required this.text3, required this.gold, required this.goldDim,
    required this.ok, required this.warn, required this.danger, required this.info, required this.dark,
  });

  static const grafito = Paleta(
    bg: Color(0xFF0A0B0D), surface: Color(0xFF111316), surface2: Color(0xFF171A1E),
    line: Color(0x14FFFFFF), line2: Color(0x24FFFFFF),
    text: Color(0xFFEDEEF0), text2: Color(0xFFA2A8B0), text3: Color(0xFF666D76),
    gold: Color(0xFFC9A86A), goldDim: Color(0xFF7D6A45),
    ok: Color(0xFF4DB38B), warn: Color(0xFFE2A54B), danger: Color(0xFFE5574F), info: Color(0xFF7EA8D6),
    dark: true,
  );
  static const porcelana = Paleta(
    bg: Color(0xFFF3F2EE), surface: Color(0xFFFFFFFF), surface2: Color(0xFFF7F6F3),
    line: Color(0x16000000), line2: Color(0x26000000),
    text: Color(0xFF111215), text2: Color(0xFF4C5159), text3: Color(0xFF8B9099),
    gold: Color(0xFF9B7838), goldDim: Color(0xFFC9B48A),
    ok: Color(0xFF23855D), warn: Color(0xFFB3741A), danger: Color(0xFFC63A31), info: Color(0xFF3F6E9F),
    dark: false,
  );

  Color severity(int s) => switch (s) { >= 5 => danger, 4 => const Color(0xFFE07A3E), 3 => warn, 2 => text2, _ => text3 };
  Color verdict(String? v) => switch (v) { 'ok' => ok, 'sospechoso' => warn, 'manipulado' => danger, _ => text3 };
  Color health(num s) => s >= 85 ? ok : s >= 65 ? gold : s >= 40 ? warn : danger;

  @override
  Paleta copyWith() => this;
  @override
  Paleta lerp(Paleta? other, double t) => t < 0.5 ? this : (other ?? this);
}

extension PaletaX on BuildContext {
  Paleta get p => Theme.of(this).extension<Paleta>()!;
}

const fSans = 'Inter';
const fMono = 'PlexMono';
const tabular = [FontFeature.tabularFigures()];

/// Texto base. [w] peso, [ls] espaciado.
TextStyle tx(BuildContext c, double size, {FontWeight w = FontWeight.w400, Color? color, double ls = 0, double h = 1.35}) =>
    TextStyle(fontFamily: fSans, fontSize: size, fontWeight: w, color: color ?? c.p.text, letterSpacing: ls,
        height: h, fontFeatures: tabular);

/// Etiqueta en versalitas espaciadas (encabezados de sección, unidades).
TextStyle label(BuildContext c, {Color? color, double size = 10.5}) =>
    TextStyle(fontFamily: fSans, fontSize: size, fontWeight: FontWeight.w600, letterSpacing: 1.7,
        color: color ?? c.p.text3, height: 1.2);

/// Cifras grandes y ligeras, como en un cuadro de instrumentos.
TextStyle num_(BuildContext c, double size, {FontWeight w = FontWeight.w300, Color? color}) =>
    TextStyle(fontFamily: fSans, fontSize: size, fontWeight: w, color: color ?? c.p.text, letterSpacing: -0.5,
        height: 1.0, fontFeatures: tabular);

TextStyle mono(BuildContext c, double size, {FontWeight w = FontWeight.w400, Color? color}) =>
    TextStyle(fontFamily: fMono, fontSize: size, fontWeight: w, color: color ?? c.p.text2, height: 1.3);

const difficultyLabels = {
  1: 'Lo resuelve el operador',
  2: 'Mecánico, sin complicación',
  3: 'Mecánico con experiencia',
  4: 'Especialista',
  5: 'Taller oficial · software de marca',
};
const severityLabels = {1: 'Informativa', 2: 'Leve', 3: 'Moderada', 4: 'Grave', 5: 'Crítica'};

ThemeData buildTheme(Paleta k) {
  final b = k.dark ? Brightness.dark : Brightness.light;
  final scheme = ColorScheme.fromSeed(seedColor: k.gold, brightness: b, primary: k.gold, surface: k.bg, onSurface: k.text);
  return ThemeData(
    useMaterial3: true,
    brightness: b,
    colorScheme: scheme,
    fontFamily: fSans,
    scaffoldBackgroundColor: k.bg,
    extensions: [k],
    dividerColor: k.line,
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: AppBarTheme(backgroundColor: k.bg, foregroundColor: k.text, elevation: 0, scrolledUnderElevation: 0),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: k.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: k.line2)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: k.line2)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: k.gold)),
      labelStyle: TextStyle(color: k.text3, fontFamily: fSans),
      hintStyle: TextStyle(color: k.text3, fontFamily: fSans),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: k.surface2, behavior: SnackBarBehavior.floating,
      contentTextStyle: TextStyle(color: k.text, fontFamily: fSans),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10), side: BorderSide(color: k.line2)),
    ),
    popupMenuTheme: PopupMenuThemeData(color: k.surface2, textStyle: TextStyle(color: k.text, fontFamily: fSans)),
  );
}
