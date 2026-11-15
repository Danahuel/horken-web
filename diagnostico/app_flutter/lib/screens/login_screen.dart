import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../widgets/common.dart';

/// Solo entran las cuentas que creó el asistente del portátil (tú y tu mecánico).
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
      setState(() => _error = switch (e.code) {
            'invalid-credential' || 'wrong-password' || 'user-not-found' => 'Email o contraseña incorrectos.',
            'network-request-failed' => 'Sin conexión a internet.',
            _ => 'No se pudo entrar (${e.code}).',
          });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    return Scaffold(
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.fromLTRB(24, 48, 24, 24), children: [
          Text('HORKEN', style: cond(context, 44, w: FontWeight.w700, ls: 6)),
          Text('diagnóstico de maquinaria', style: mono(context, 13, color: k.ink2)),
          const SizedBox(height: 36),
          const Rule(strong: true),
          const SizedBox(height: 16),
          TextField(controller: _email, keyboardType: TextInputType.emailAddress, autofillHints: const [AutofillHints.email],
              style: body(context, 16), decoration: const InputDecoration(labelText: 'Email')),
          const SizedBox(height: 12),
          TextField(controller: _pass, obscureText: true, onSubmitted: (_) => _login(),
              style: body(context, 16), decoration: const InputDecoration(labelText: 'Contraseña')),
          if (_error != null) Padding(padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, style: body(context, 14, color: k.danger))),
          const SizedBox(height: 28),
          InkButton('Entrar', onTap: _login, busy: _busy),
          const SizedBox(height: 16),
          Text('La contraseña te llegó en el email de bienvenida.', style: body(context, 13, color: k.ink3)),
        ]),
      ),
    );
  }
}
