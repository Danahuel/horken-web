import 'package:flutter/material.dart';

const kAmber = Color(0xFFFFB300);
const kBg = Color(0xFF121212);
const kCard = Color(0xFF1E1E1E);
const kCard2 = Color(0xFF262626);

const severityColors = {
  0: Color(0xFF607D8B),
  1: Color(0xFF43A047),
  2: Color(0xFF7CB342),
  3: Color(0xFFFBC02D),
  4: Color(0xFFFB8C00),
  5: Color(0xFFE53935),
};

const severityLabels = {1: 'Leve', 2: 'Baja', 3: 'Media', 4: 'Alta', 5: 'Crítica'};
const difficultyLabels = {
  1: 'Muy fácil · operador',
  2: 'Fácil · mecánico básico',
  3: 'Media · mecánico con experiencia',
  4: 'Difícil · especialista',
  5: 'Muy difícil · taller oficial / software de marca',
};

Color verdictColor(String? v) => switch (v) {
      'ok' => const Color(0xFF43A047),
      'sospechoso' => const Color(0xFFFB8C00),
      'manipulado' => const Color(0xFFE53935),
      _ => const Color(0xFF757575),
    };

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: kAmber, brightness: Brightness.dark, primary: kAmber, surface: kBg);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: kBg,
    cardTheme: const CardThemeData(color: kCard, margin: EdgeInsets.zero, elevation: 0),
    appBarTheme: const AppBarTheme(backgroundColor: kBg, elevation: 0, centerTitle: false),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: const Color(0xFF181818),
      indicatorColor: kAmber.withValues(alpha: 0.25),
      labelTextStyle: WidgetStateProperty.all(const TextStyle(fontSize: 11)),
    ),
  );
}
