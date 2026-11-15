import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'session.dart';

abstract class SessionRepository {
  Stream<List<Session>> sessions();
  Stream<Session?> session(String id);
  Future<void> requestReport(String id, List<String> recipients);
  Future<void> saveRecipients(String id, List<String> recipients);
  bool get isDemo;
}

/// Tiempo real a través de Firestore (lo que usaréis tú y tu mecánico).
class FirestoreRepository implements SessionRepository {
  final _col = FirebaseFirestore.instance.collection('sessions');

  @override
  bool get isDemo => false;

  @override
  Stream<List<Session>> sessions() => _col
      .orderBy('created_at', descending: true)
      .limit(100)
      .snapshots()
      .map((q) => q.docs.map((d) => Session(d.id, d.data())).toList());

  @override
  Stream<Session?> session(String id) =>
      _col.doc(id).snapshots().map((d) => d.exists ? Session(d.id, d.data()!) : null);

  @override
  Future<void> requestReport(String id, List<String> recipients) => _col.doc(id).update({
        'recipients': recipients,
        'report_request': {'pending': true, 'recipients': recipients, 'at': FieldValue.serverTimestamp()},
      });

  @override
  Future<void> saveRecipients(String id, List<String> recipients) =>
      _col.doc(id).update({'recipients': recipients});
}

/// Modo demostración: datos generados por el simulador Python, con valores
/// en vivo que se mueven cada segundo. Se usa si Firebase no está configurado.
class DemoRepository implements SessionRepository {
  final _rnd = Random();
  final Map<String, Map<String, dynamic>> _data = {};
  final _ctrl = StreamController<void>.broadcast();
  Timer? _timer;
  int _tick = 0;

  @override
  bool get isDemo => true;

  Future<void> load() async {
    for (final name in ['cat320', 'arjes', 'hamm']) {
      final j = jsonDecode(await rootBundle.loadString('assets/demo/$name.json')) as Map<String, dynamic>;
      j['status'] = name == 'cat320' ? 'live' : 'finished';
      _data[name] = j;
    }
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _animate());
  }

  void _animate() {
    _tick++;
    final live = (_data['cat320']!['live'] as Map).cast<String, dynamic>();
    final w = (sin(_tick / 5) + 1) / 2;
    void set(String k, double v) {
      if (live[k] != null) live[k] = {...(live[k] as Map), 'value': double.parse(v.toStringAsFixed(1))};
    }

    set('rpm', 850 + w * 950 + _rnd.nextDouble() * 20);
    set('oil_pressure_kpa', 150 * (0.7 + 0.3 * w) + _rnd.nextDouble() * 6);
    set('coolant_c', min(96.0, 80 + _tick * 0.3) + _rnd.nextDouble());
    set('hyd_oil_temp_c', min(94.0, 64 + _tick * 0.4) + _rnd.nextDouble());
    set('boost_kpa', 60 + 120 * w + _rnd.nextDouble() * 4);
    set('fuel_rate_lh', 6 + 16 * w + _rnd.nextDouble());
    set('torque_pct', 20 + 55 * w);
    set('battery_v', 27.5 + _rnd.nextDouble() * 0.2);
    _data['cat320']!['updated_at'] = DateTime.now().toUtc().toIso8601String();
    final s = (_data['cat320']!['summary'] as Map);
    s['frames'] = ((s['frames'] as num) + 120 + _rnd.nextInt(10)).toInt();
    _ctrl.add(null);
  }

  Session _s(String id) => Session(id, _data[id]!);

  @override
  Stream<List<Session>> sessions() async* {
    yield _data.keys.map(_s).toList();
    await for (final _ in _ctrl.stream) {
      yield _data.keys.map(_s).toList();
    }
  }

  @override
  Stream<Session?> session(String id) async* {
    yield _s(id);
    await for (final _ in _ctrl.stream) {
      yield _s(id);
    }
  }

  @override
  Future<void> requestReport(String id, List<String> recipients) async {
    _data[id]!['recipients'] = recipients;
    await Future.delayed(const Duration(seconds: 2));
    _data[id]!['report_status'] = {'ok': true, 'to': recipients, 'at': DateTime.now().toIso8601String(), 'demo': true};
    _ctrl.add(null);
  }

  @override
  Future<void> saveRecipients(String id, List<String> recipients) async {
    _data[id]!['recipients'] = recipients;
    _ctrl.add(null);
  }

  void dispose() => _timer?.cancel();
}
