import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/app_config.dart';
import '../theme.dart';
import '../widgets/brand.dart';
import '../widgets/instruments.dart';

class SetupScreen extends StatefulWidget {
  final String? error;
  final Future<void> Function(String code) onSaved;
  final VoidCallback onDemo;
  const SetupScreen({super.key, this.error, required this.onSaved, required this.onDemo});
  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  final _ctrl = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _paste() async {
    final d = await Clipboard.getData('text/plain');
    if (d?.text != null) setState(() => _ctrl.text = d!.text!.trim());
  }

  Future<void> _save() async {
    if (AppConfig.parse(_ctrl.text) == null) {
      setState(() => _error = 'El código no es válido. Debe empezar por MDK1:');
      return;
    }
    setState(() => _busy = true);
    await widget.onSaved(_ctrl.text);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    final err = _error ?? widget.error;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(padding: const EdgeInsets.fromLTRB(28, 64, 28, 28), children: [
              const Wordmark(size: 17, tagline: true),
              const SizedBox(height: 64),
              Text('Activar este dispositivo', style: tx(context, 26, w: FontWeight.w300, h: 1.2)),
              const SizedBox(height: 12),
              Text('Introduzca el código de activación recibido por correo al configurar el equipo de lectura. '
                  'Solo es necesario la primera vez.', style: tx(context, 14.5, color: p.text2, h: 1.55)),
              const SizedBox(height: 28),
              Text('CÓDIGO DE ACTIVACIÓN', style: label(context)),
              const SizedBox(height: 10),
              TextField(
                controller: _ctrl, minLines: 3, maxLines: 5, style: mono(context, 12.5, color: p.text),
                decoration: InputDecoration(
                  hintText: 'MDK1:…',
                  suffixIcon: IconButton(icon: Icon(Icons.content_paste_rounded, color: p.text3, size: 20),
                      onPressed: _paste, tooltip: 'Pegar'),
                ),
              ),
              if (err != null) Padding(padding: const EdgeInsets.only(top: 12),
                  child: Text(err, style: tx(context, 13, color: p.danger))),
              const SizedBox(height: 28),
              GoldButton('Activar', onTap: _save, busy: _busy),
              const SizedBox(height: 14),
              GoldButton('Ver demostración', onTap: widget.onDemo, outline: true),
              const SizedBox(height: 48),
              Center(child: Text('Uso interno · acceso restringido', style: tx(context, 11.5, color: p.text3))),
            ]),
          ),
        ),
      ),
    );
  }
}
