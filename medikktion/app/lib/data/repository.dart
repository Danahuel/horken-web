import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'session.dart';

abstract class SessionRepository {
  Stream<List<Session>> sessions();
  Stream<Session?> session(String id);
  Future<void> requestReport(String id, List<String> recipients, {String lang = 'es'});
  Future<void> saveRecipients(String id, List<String> recipients);
  /// Fotos y notas del taller de una lectura (más recientes primero).
  Stream<List<Map<String, dynamic>>> journal(String id);
  Future<void> addJournal(String id, Map<String, dynamic> entry);
  /// Reparación hecha: coste y horas reales (el portátil aprende de ellas los precios).
  Future<void> addWorkOrder(String id, Map<String, dynamic> wo);
  /// Pide al portátil empezar o parar la grabación de tramas.
  Future<void> requestRecording(String id, bool active);
  bool get isDemo;
}

/// Tiempo real a través de Firestore (lo que usáis tú y tu mecánico).
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
  Future<void> requestReport(String id, List<String> recipients, {String lang = 'es'}) => _col.doc(id).update({
        'recipients': recipients,
        'report_request': {'pending': true, 'recipients': recipients, 'lang': lang, 'at': FieldValue.serverTimestamp()},
      });

  @override
  Future<void> saveRecipients(String id, List<String> recipients) =>
      _col.doc(id).update({'recipients': recipients});

  @override
  Stream<List<Map<String, dynamic>>> journal(String id) => _col.doc(id).collection('bitacora')
      .orderBy('at', descending: true).limit(60).snapshots()
      .map((q) => q.docs.map((d) => d.data()).toList());

  @override
  Future<void> addJournal(String id, Map<String, dynamic> entry) =>
      _col.doc(id).collection('bitacora').add({...entry, 'at': DateTime.now().toUtc().toIso8601String()});

  @override
  Future<void> addWorkOrder(String id, Map<String, dynamic> wo) => _col.doc(id).update({
        'work_orders': FieldValue.arrayUnion([wo]),
        'has_work_orders': true,
      });

  @override
  Future<void> requestRecording(String id, bool active) => _col.doc(id).update({
        'record_request': {'pending': true, 'active': active, 'at': FieldValue.serverTimestamp()},
      });
}

/// Simulación de una medida en vivo a partir de su propio historial: sigue la
/// tendencia que traía (las temperaturas suben o bajan de centésima en centésima)
/// con el ruido fino de un sensor real.
class _Signal {
  final String key;
  double v, mean, sd, drift;
  _Signal(this.key, this.v, this.mean, this.sd, this.drift);
}

const _thermal = {'coolant_c', 'oil_temp_c', 'hyd_oil_temp_c', 'trans_oil_temp_c', 'intake_temp_c', 'ambient_c', 'fuel_temp_c'};
const _cyclic = {'rpm', 'boost_kpa', 'fuel_rate_lh', 'torque_pct', 'pump1_bar', 'pump2_bar'};

class DemoRepository implements SessionRepository {
  static const names = ['cat320', 'fuchs', 'arjes', 'hamm'];
  final _rnd = Random(42);
  final Map<String, Map<String, dynamic>> _data = {};
  final Map<String, Map<String, _Signal>> _sig = {};
  final _ctrl = StreamController<void>.broadcast();
  Timer? _timer;
  int _tick = 0;
  /// Prueba de corte: abrir la demo con ?corte=1 deja la Fuchs sin señal.
  final Set<String> _cut = Uri.base.queryParameters['corte'] == '1' ? {'fuchs'} : {};

  @override
  bool get isDemo => true;

  double _gauss() {
    final u1 = max(1e-9, _rnd.nextDouble()), u2 = _rnd.nextDouble();
    return sqrt(-2 * log(u1)) * cos(2 * pi * u2);
  }

  Future<void> load() async {
    final now = DateTime.now();
    for (final name in names) {
      final j = jsonDecode(await rootBundle.loadString('assets/demo/$name.json')) as Map<String, dynamic>;
      // Las demos se generaron en otro momento: se trasladan a "ahora".
      final updated = DateTime.tryParse('${j['updated_at']}') ?? now;
      final shift = now.difference(updated).inMilliseconds / 1000.0;
      final live = j['status'] == 'live';
      final endShift = live ? shift : shift - 60 * 60 * (2 + names.indexOf(name) * 9);
      for (final tr in ((j['trend'] as Map?) ?? {}).values) {
        tr['t'] = [for (final t in (tr['t'] as List)) (t as num) + endShift];
      }
      String mv(String k) => DateTime.parse('${j[k]}').add(Duration(milliseconds: (endShift * 1000).round()))
          .toUtc().toIso8601String();
      j['updated_at'] = mv('updated_at');
      if (j['started_at'] != null) j['started_at'] = mv('started_at');
      if (_cut.contains(name)) {
        j['updated_at'] = now.subtract(const Duration(seconds: 95)).toUtc().toIso8601String();
      }
      _data[name] = j;
      _sig[name] = _signals(j);
    }
    _timer = Timer.periodic(const Duration(milliseconds: 1000), (_) => _step());
  }

  Map<String, _Signal> _signals(Map<String, dynamic> j) {
    final out = <String, _Signal>{};
    final trend = (j['trend'] as Map?) ?? {};
    ((j['live'] as Map?) ?? {}).forEach((k, p) {
      final v = (asNum((p as Map)['value']) ?? 0).toDouble();
      var mean = v, sd = 0.0, drift = 0.0;
      final tr = trend[k] as Map?;
      if (tr != null && (tr['v'] as List).length > 10) {
        final vs = (tr['v'] as List).map((e) => (e as num).toDouble()).toList();
        final ts = (tr['t'] as List).map((e) => (e as num).toDouble()).toList();
        final last = vs.sublist(max(0, vs.length - 40));
        mean = last.reduce((a, b) => a + b) / last.length;
        sd = sqrt(last.map((x) => (x - mean) * (x - mean)).reduce((a, b) => a + b) / last.length);
        final n = min(60, vs.length - 1);
        drift = ((vs.last - vs[vs.length - 1 - n]) / max(1.0, ts.last - ts[ts.length - 1 - n])).clamp(-0.02, 0.02);
      }
      out['$k'] = _Signal('$k', v, mean, sd, drift);
    });
    return out;
  }

  void _step() {
    _tick++;
    for (final name in names) {
      final j = _data[name]!;
      if (j['status'] != 'live' || _cut.contains(name)) continue;
      final sig = _sig[name]!;
      final live = (j['live'] as Map).cast<String, dynamic>();
      final phase = sin(2 * pi * _tick / (20 + names.indexOf(name) * 4));
      final rpm = sig['rpm'];
      for (final s in sig.values) {
        if (_thermal.contains(s.key)) {
          // termómetro: tendencia lenta + ruido de centésimas
          s.v += s.drift * (0.6 + _rnd.nextDouble() * 0.8) + _gauss() * 0.006;
        } else if (_cyclic.contains(s.key)) {
          final target = s.mean + max(s.sd, s.mean * 0.04) * 1.25 * phase + _gauss() * s.sd * 0.15;
          s.v += (target - s.v) * 0.55;
        } else if (s.key == 'oil_pressure_kpa' && rpm != null && rpm.mean > 0) {
          final target = s.mean * pow(max(300.0, rpm.v) / rpm.mean, 0.65) + _gauss() * 1.5;
          s.v += (target - s.v) * 0.6;
        } else if (s.key.endsWith('_pct')) {
          s.v -= 0.0015 + _rnd.nextDouble() * 0.001;
        } else {
          s.v += (s.mean - s.v) * 0.08 + _gauss() * max(0.004, s.sd * 0.1);
        }
        if (live[s.key] != null) live[s.key] = {...(live[s.key] as Map), 'value': s.v};
      }
      final now = DateTime.now();
      j['updated_at'] = now.toUtc().toIso8601String();
      final sum = j['summary'] as Map;
      final add = 118 + _rnd.nextInt(9);
      sum['frames'] = ((sum['frames'] as num) + add).toInt();
      final rec = j['recording'] as Map?;
      if (rec != null && rec['active'] == true) {
        rec['frames'] = (rec['frames'] as num) + add;
        rec['mb'] = (rec['frames'] as num) * 0.000021;  // ~22 bytes por trama comprimida
      }
      if (_tick % 5 == 0) {
        final t = now.millisecondsSinceEpoch / 1000.0;
        ((j['trend'] as Map?) ?? {}).forEach((k, tr) {
          final s = sig[k];
          if (s == null) return;
          (tr['t'] as List).add(t);
          (tr['v'] as List).add(s.v);
          if ((tr['t'] as List).length > 180) {
            (tr['t'] as List).removeAt(0);
            (tr['v'] as List).removeAt(0);
          }
        });
      }
    }
    _ctrl.add(null);
  }

  Session _s(String id) => Session(id, _data[id]!);

  @override
  Stream<List<Session>> sessions() async* {
    yield names.map(_s).toList();
    await for (final _ in _ctrl.stream) {
      yield names.map(_s).toList();
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
  Future<void> requestReport(String id, List<String> recipients, {String lang = 'es'}) async {
    _data[id]!['recipients'] = recipients;
    await Future.delayed(const Duration(milliseconds: 1600));
    _data[id]!['report_status'] = {'ok': true, 'to': recipients, 'at': DateTime.now().toIso8601String(), 'demo': true};
    _ctrl.add(null);
  }

  @override
  Future<void> saveRecipients(String id, List<String> recipients) async {
    _data[id]!['recipients'] = recipients;
    _ctrl.add(null);
  }

  final Map<String, List<Map<String, dynamic>>> _journal = {
    'cat320': [
      {'type': 'nota', 'text': 'Fuga de aceite en el latiguillo del brazo, lado izquierdo. El vendedor dice que '
          'el cuadro "siempre ha marcado esas horas".', 'by': 'mecánico', 'at': '2026-11-18T10:41:00Z'},
    ],
  };
  final _jctrl = StreamController<void>.broadcast();

  @override
  Stream<List<Map<String, dynamic>>> journal(String id) async* {
    yield List.of(_journal[id] ?? []);
    await for (final _ in _jctrl.stream) {
      yield List.of(_journal[id] ?? []);
    }
  }

  @override
  Future<void> addJournal(String id, Map<String, dynamic> entry) async {
    _journal.putIfAbsent(id, () => []).insert(0, {...entry, 'at': DateTime.now().toUtc().toIso8601String()});
    _jctrl.add(null);
  }

  @override
  Future<void> addWorkOrder(String id, Map<String, dynamic> wo) async {
    final j = _data[id]!;
    j['work_orders'] = [...((j['work_orders'] as List?) ?? []), wo];
    _ctrl.add(null);
  }

  @override
  Future<void> requestRecording(String id, bool active) async {
    final j = _data[id]!;
    j['record_request'] = {'pending': true, 'active': active};
    _ctrl.add(null);
    await Future.delayed(const Duration(milliseconds: 900)); // lo que tarda el portátil en responder
    final now = DateTime.now().toUtc();
    j['record_request'] = {'pending': false, 'active': active};
    j['recording'] = active
        ? {'active': true, 'file': '${j['session_id']}.blf', 'frames': 0, 'mb': 0.0, 'since': now.toIso8601String()}
        : {...((j['recording'] as Map?) ?? {}), 'active': false};
    _ctrl.add(null);
  }

  void dispose() => _timer?.cancel();
}
