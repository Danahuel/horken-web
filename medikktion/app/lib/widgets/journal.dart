import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../data/repository.dart';
import '../data/session.dart';
import '../theme.dart';
import 'instruments.dart';

/// Fotos y notas del taller. Las fotos se comprimen en el móvil (~150 KB) y se
/// guardan en la base de datos: no hace falta el plan de pago de Firebase.
class JournalPanel extends StatefulWidget {
  final Session s;
  final SessionRepository repo;
  const JournalPanel({super.key, required this.s, required this.repo});
  @override
  State<JournalPanel> createState() => _JournalPanelState();
}

class _JournalPanelState extends State<JournalPanel> {
  bool _busy = false;

  String? get _who {
    try {
      return FirebaseAuth.instance.currentUser?.email;
    } catch (_) {
      return null;
    }
  }

  Future<void> _photo(ImageSource src) async {
    final x = await ImagePicker().pickImage(source: src, maxWidth: 1280, maxHeight: 1280, imageQuality: 55);
    if (x == null) return;
    setState(() => _busy = true);
    final bytes = await x.readAsBytes();
    if (bytes.length > 700 * 1024) {
      if (mounted) {
        setState(() => _busy = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('La foto es demasiado grande.')));
      }
      return;
    }
    if (!mounted) return;
    final note = await _ask('Pie de foto (opcional)');
    await widget.repo.addJournal(widget.s.id, {'type': 'foto', 'image': base64Encode(bytes), 'text': note ?? '',
      'by': _who ?? 'demostración'});
    if (mounted) setState(() => _busy = false);
  }

  Future<void> _note() async {
    final t = await _ask('Nota del taller', lines: 4);
    if (t == null || t.trim().isEmpty) return;
    await widget.repo.addJournal(widget.s.id, {'type': 'nota', 'text': t.trim(), 'by': _who ?? 'demostración'});
  }

  Future<String?> _ask(String title, {int lines = 2}) {
    final c = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: context.p.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: Text(title, style: tx(context, 16)),
        content: TextField(controller: c, minLines: lines, maxLines: lines + 2, autofocus: true, style: tx(context, 14)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text('Cancelar', style: tx(context, 13, color: context.p.text3))),
          TextButton(onPressed: () => Navigator.pop(ctx, c.text),
              child: Text('Guardar', style: tx(context, 13, color: context.p.gold, w: FontWeight.w600))),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final p = context.p;
    return StreamBuilder<List<Map<String, dynamic>>>(
      stream: widget.repo.journal(widget.s.id),
      builder: (context, snap) {
        final items = snap.data ?? const [];
        final photos = items.where((e) => e['type'] == 'foto' && e['image'] != null).toList();
        final notes = items.where((e) => e['type'] == 'nota').toList();
        return Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(child: Text('${photos.length} fotos · ${notes.length} notas', style: tx(context, 13, color: p.text2))),
              if (_busy) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 1.4)),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: _btn(context, Icons.photo_camera_outlined, 'Foto', () => _photo(ImageSource.camera))),
              const SizedBox(width: 8),
              Expanded(child: _btn(context, Icons.photo_library_outlined, 'Galería', () => _photo(ImageSource.gallery))),
              const SizedBox(width: 8),
              Expanded(child: _btn(context, Icons.edit_note_rounded, 'Nota', _note)),
            ]),
            if (photos.isNotEmpty) ...[
              const SizedBox(height: 14),
              GridView.count(
                crossAxisCount: 3, shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 6, crossAxisSpacing: 6,
                children: [
                  for (final ph in photos)
                    GestureDetector(
                      onTap: () => _open(context, ph),
                      child: ClipRRect(borderRadius: BorderRadius.circular(8),
                          child: Image.memory(base64Decode('${ph['image']}'), fit: BoxFit.cover, gaplessPlayback: true)),
                    ),
                ],
              ),
            ],
            for (final n in notes)
              Container(
                margin: const EdgeInsets.only(top: 12),
                padding: const EdgeInsets.only(left: 12),
                decoration: BoxDecoration(border: Border(left: BorderSide(color: p.goldDim, width: 2))),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('${n['text']}', style: tx(context, 13.5, h: 1.5)),
                  const SizedBox(height: 4),
                  Text('${n['by'] ?? ''} · ${whenText(DateTime.tryParse('${n['at']}')?.toLocal())}',
                      style: tx(context, 11, color: p.text3)),
                ]),
              ),
          ]),
        );
      },
    );
  }

  Widget _btn(BuildContext c, IconData i, String t, VoidCallback onTap) => OutlinedButton.icon(
        onPressed: _busy ? null : onTap,
        icon: Icon(i, size: 17, color: c.p.gold),
        label: Text(t, style: tx(c, 12.5)),
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(vertical: 12),
          side: BorderSide(color: c.p.line2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        ),
      );

  void _open(BuildContext c, Map ph) => Navigator.push(c, MaterialPageRoute(builder: (_) => Scaffold(
        backgroundColor: Colors.black,
        appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white,
            title: Text('${ph['text'] ?? ''}', style: const TextStyle(fontSize: 14))),
        body: Center(child: InteractiveViewer(child: Image.memory(base64Decode('${ph['image']}')))),
      )));
}
