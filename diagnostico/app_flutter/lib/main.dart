import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'data/repository.dart';
import 'firebase_options.dart';
import 'screens/login_screen.dart';
import 'screens/sessions_screen.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SessionRepository repo;
  try {
    await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
    repo = FirestoreRepository();
  } catch (_) {
    final demo = DemoRepository();
    await demo.load();
    repo = demo;
  }
  runApp(HorkenApp(repo: repo));
}

class HorkenApp extends StatelessWidget {
  final SessionRepository repo;
  const HorkenApp({super.key, required this.repo});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Horken Diagnóstico',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: repo.isDemo
          ? SessionsScreen(repo: repo)
          : StreamBuilder<User?>(
              stream: FirebaseAuth.instance.authStateChanges(),
              builder: (context, snap) => snap.data == null ? const LoginScreen() : SessionsScreen(repo: repo),
            ),
    );
  }
}
