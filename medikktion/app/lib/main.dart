import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'data/app_config.dart';
import 'data/repository.dart';
import 'screens/fleet_screen.dart';
import 'screens/login_screen.dart';
import 'screens/setup_screen.dart';
import 'theme.dart';

/// Tema claro (porcelana) u oscuro (grafito, por defecto).
final lightMode = ValueNotifier<bool>(false);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  lightMode.value = await AppConfig.lightTheme();
  runApp(const MedikktionApp());
}

class MedikktionApp extends StatelessWidget {
  const MedikktionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool>(
      valueListenable: lightMode,
      builder: (_, light, _) {
        SystemChrome.setSystemUIOverlayStyle(light ? SystemUiOverlayStyle.dark : SystemUiOverlayStyle.light);
        return MaterialApp(
          title: 'Medikktion',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(light ? Paleta.porcelana : Paleta.grafito),
          home: const Boot(),
        );
      },
    );
  }
}

/// Arranque: con código de Firebase guardado → conecta; si no → bienvenida.
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
        _error = 'No se pudo conectar con ese código.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_repo != null) {
      final repo = _repo!;
      if (repo.isDemo) return FleetScreen(repo: repo, onExitDemo: () => setState(() => _repo = null));
      return StreamBuilder<User?>(
        stream: FirebaseAuth.instance.authStateChanges(),
        builder: (_, snap) => snap.data == null ? const LoginScreen() : FleetScreen(repo: repo),
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
