import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'data/app_config.dart';
import 'data/repository.dart';
import 'screens/login_screen.dart';
import 'screens/sessions_screen.dart';
import 'screens/setup_screen.dart';
import 'theme.dart';

/// Tema día/noche compartido por toda la app.
final nightMode = ValueNotifier<bool>(false);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  nightMode.value = await AppConfig.nightTheme();
  runApp(const HorkenApp());
}

class HorkenApp extends StatelessWidget {
  const HorkenApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: nightMode,
      builder: (_, night, _) => MaterialApp(
        title: 'Horken',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(night ? Tinta.night : Tinta.day, night ? Brightness.dark : Brightness.light),
        home: const Boot(),
      ),
    );
  }
}

/// Arranque: ¿hay código de Firebase guardado? → conecta; si no → pantalla de configuración.
class Boot extends StatefulWidget {
  const Boot({super.key});
  @override
  State<Boot> createState() => _BootState();
}

class _BootState extends State<Boot> {
  SessionRepository? _repo;
  bool _needsSetup = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start({bool demo = false}) async {
    if (demo) {
      final d = DemoRepository();
      await d.load();
      setState(() => _repo = d);
      return;
    }
    final code = await AppConfig.savedCode();
    final options = code == null ? null : AppConfig.parse(code);
    if (options == null) {
      setState(() => _needsSetup = true);
      return;
    }
    try {
      if (Firebase.apps.isEmpty) await Firebase.initializeApp(options: options);
      setState(() {
        _repo = FirestoreRepository();
        _needsSetup = false;
      });
    } catch (e) {
      setState(() {
        _needsSetup = true;
        _error = 'No se pudo conectar con ese código ($e)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_repo != null) {
      final repo = _repo!;
      if (repo.isDemo) return SessionsScreen(repo: repo, onExitDemo: () => setState(() => _repo = null));
      return StreamBuilder<User?>(
        stream: FirebaseAuth.instance.authStateChanges(),
        builder: (_, snap) => snap.data == null ? const LoginScreen() : SessionsScreen(repo: repo),
      );
    }
    if (_needsSetup) {
      return SetupScreen(
        error: _error,
        onSaved: (code) async {
          await AppConfig.saveCode(code);
          setState(() => _error = null);
          await _start();
        },
        onDemo: () => _start(demo: true),
      );
    }
    return const Scaffold(body: SizedBox());
  }
}
