import 'dart:convert';

import 'package:firebase_core/firebase_core.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// La app no lleva datos de Firebase dentro: se configura pegando el código
/// que genera el portátil (`python -m medikktion configurar`). Así el mismo
/// APK vale para cualquier proyecto y no hace falta compilar nada.
class AppConfig {
  static const _kCode = 'codigo_firebase';
  static const _kTheme = 'tema_claro';

  static FirebaseOptions? parse(String text) {
    text = text.trim();
    Map<String, dynamic>? d;
    try {
      if (text.startsWith('MDK1:')) {
        var raw = text.substring(5).replaceAll(RegExp(r'\s'), '');
        raw = raw.padRight(raw.length + (4 - raw.length % 4) % 4, '=');
        d = jsonDecode(utf8.decode(base64Url.decode(raw))) as Map<String, dynamic>;
      } else if (text.startsWith('{')) {
        // También vale pegar el google-services.json entero
        final gs = jsonDecode(text) as Map<String, dynamic>;
        final c = (gs['client'] as List).first as Map;
        d = {
          'k': ((c['api_key'] as List).first as Map)['current_key'],
          'a': (c['client_info'] as Map)['mobilesdk_app_id'],
          'p': (gs['project_info'] as Map)['project_id'],
          's': (gs['project_info'] as Map)['project_number'],
          'b': (gs['project_info'] as Map)['storage_bucket'] ?? '',
        };
      }
    } catch (_) {
      return null;
    }
    if (d == null || d['k'] == null || d['a'] == null || d['p'] == null) return null;
    return FirebaseOptions(
      apiKey: '${d['k']}', appId: '${d['a']}', projectId: '${d['p']}',
      messagingSenderId: '${d['s'] ?? ''}', storageBucket: '${d['b'] ?? ''}',
    );
  }

  static Future<String?> savedCode() async => (await SharedPreferences.getInstance()).getString(_kCode);
  static Future<void> saveCode(String code) async => (await SharedPreferences.getInstance()).setString(_kCode, code.trim());
  static Future<void> clearCode() async => (await SharedPreferences.getInstance()).remove(_kCode);

  static Future<bool> lightTheme() async => (await SharedPreferences.getInstance()).getBool(_kTheme) ?? false;
  static Future<void> setLightTheme(bool v) async => (await SharedPreferences.getInstance()).setBool(_kTheme, v);
}
