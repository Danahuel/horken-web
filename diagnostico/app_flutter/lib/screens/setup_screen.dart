import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../data/app_config.dart';
import '../theme.dart';
import '../widgets/common.dart';

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
      setState(() => _error = 'Ese código no es válido. Tiene que empezar por HORKEN1:');
      return;
    }
    setState(() => _busy = true);
    await widget.onSaved(_ctrl.text);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final k = context.ink;
    final err = _error ?? widget.error;
    return Scaffold(
      body: SafeArea(
        child: ListView(padding: const EdgeInsets.fromLTRB(24, 48, 24, 24), children: [
          Text('HORKEN', style: cond(context, 44, w: FontWeight.w700, ls: 6)),
          Text('diagnóstico de maquinaria', style: mono(context, 13, color: k.ink2)),
          const SizedBox(height: 36),
          const Rule(strong: true),
          const SizedBox(height: 20),
          Text('Primera vez', style: cond(context, 22, w: FontWeight.w700)),
          const SizedBox(height: 8),
          Text('Pega el código que te llegó por email al configurar el portátil '
              '(empieza por HORKEN1:). Solo hay que hacerlo una vez.',
              style: body(context, 15, color: k.ink2)),
          const SizedBox(height: 18),
          TextField(
            controller: _ctrl, minLines: 2, maxLines: 5,
            style: mono(context, 12),
            decoration: InputDecoration(hintText: 'HORKEN1:eyJrIjoi…',
                suffixIcon: IconButton(icon: Icon(Icons.content_paste, color: k.ink2), onPressed: _paste, tooltip: 'Pegar')),
          ),
          if (err != null) Padding(padding: const EdgeInsets.only(top: 10),
              child: Text(err, style: body(context, 13, color: k.danger))),
          const SizedBox(height: 24),
          InkButton('Guardar y entrar', onTap: _save, busy: _busy),
          const SizedBox(height: 28),
          const Rule(),
          TextButton(
            onPressed: widget.onDemo,
            style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16), alignment: Alignment.centerLeft),
            child: Text('Antes, ver cómo funciona con máquinas de prueba →',
                style: body(context, 15, w: FontWeight.w600, color: k.accent)),
          ),
          const Rule(),
        ]),
      ),
    );
  }
}
