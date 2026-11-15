import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';

import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/instruments.dart';

/// Solo entran las cuentas que creó el asistente del portátil.
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
            'invalid-credential' || 'wrong-password' || 'user-not-found' => 'Credenciales incorrectas.',
            'network-request-failed' => 'Sin conexión.',
            _ => 'No se pudo iniciar sesión (${e.code}).',
          });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(padding: const EdgeInsets.fromLTRB(28, 64, 28, 28), children: [
              const Wordmark(size: 17, tagline: true),
              const SizedBox(height: 64),
              Text('Iniciar sesión', style: tx(context, 26, w: FontWeight.w300)),
              const SizedBox(height: 28),
              Text('CORREO', style: label(context)),
              const SizedBox(height: 8),
              TextField(controller: _email, keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email], style: tx(context, 15)),
              const SizedBox(height: 18),
              Text('CONTRASEÑA', style: label(context)),
              const SizedBox(height: 8),
              TextField(controller: _pass, obscureText: true, onSubmitted: (_) => _login(), style: tx(context, 15)),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 14),
                  child: Text(_error!, style: tx(context, 13, color: p.danger))),
              const SizedBox(height: 30),
              GoldButton('Entrar', onTap: _login, busy: _busy),
              const SizedBox(height: 18),
              Text('La contraseña figura en el correo de alta.', style: tx(context, 12.5, color: p.text3)),
            ]),
          ),
        ),
      ),
    );
  }
}
