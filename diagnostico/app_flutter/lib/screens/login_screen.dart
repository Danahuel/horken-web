import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../theme.dart';

/// Acceso solo para usuarios creados en Firebase Authentication (tú y tu
/// mecánico). Las reglas de Firestore bloquean a cualquier otro.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _pass = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _login() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await FirebaseAuth.instance.signInWithEmailAndPassword(email: _email.text.trim(), password: _pass.text);
    } on FirebaseAuthException catch (e) {
      setState(() => _error = 'No se pudo entrar: ${e.code}');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(children: [
              const Icon(Icons.precision_manufacturing, size: 64, color: kAmber),
              const SizedBox(height: 12),
              const Text('HORKEN', style: TextStyle(fontSize: 30, fontWeight: FontWeight.w900, letterSpacing: 4)),
              const Text('Diagnóstico de maquinaria', style: TextStyle(color: Colors.white60)),
              const SizedBox(height: 32),
              TextField(controller: _email, keyboardType: TextInputType.emailAddress,
                  decoration: const InputDecoration(labelText: 'Email', border: OutlineInputBorder())),
              const SizedBox(height: 12),
              TextField(controller: _pass, obscureText: true, onSubmitted: (_) => _login(),
                  decoration: const InputDecoration(labelText: 'Contraseña', border: OutlineInputBorder())),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 12),
                  child: Text(_error!, style: const TextStyle(color: Colors.redAccent))),
              const SizedBox(height: 20),
              SizedBox(width: double.infinity, height: 50,
                  child: FilledButton(onPressed: _busy ? null : _login,
                      child: _busy ? const CircularProgressIndicator() : const Text('Entrar'))),
            ]),
          ),
        ),
      ),
    );
  }
}
