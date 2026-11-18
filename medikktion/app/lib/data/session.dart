/// Envoltorio sobre el documento `sessions/{id}` que escribe el portátil.
class Session {
  final String id;
  final Map<String, dynamic> raw;
  Session(this.id, this.raw);

  Map<String, dynamic> _m(String k) => (raw[k] as Map?)?.cast<String, dynamic>() ?? {};
  List<Map<String, dynamic>> _l(String k) =>
      ((raw[k] as List?) ?? []).map((e) => (e as Map).cast<String, dynamic>()).toList();

  Map<String, dynamic> get machine => _m('machine');
  Map<String, dynamic> get summary => _m('summary');
  Map<String, dynamic> get lamps => _m('lamps');
  Map<String, dynamic> get tamper => _m('tamper');
  Map<String, dynamic> get modifications => _m('modifications');
  Map<String, dynamic> get live => _m('live');
  Map<String, dynamic> get trend => _m('trend');
  Map<String, dynamic> get reportStatus => _m('report_status');
  Map<String, dynamic> get recording => _m('recording');
  bool get isRecording => recording['active'] == true;
  bool get recordRequested => (raw['record_request'] as Map?)?['pending'] == true;
  List<Map<String, dynamic>> get dtcs => _l('dtcs');
  List<Map<String, dynamic>> get ecus => _l('ecus');
  List<String> get recipients => ((raw['recipients'] as List?) ?? []).map((e) => '$e').toList();
  List<String> get protocols => ((raw['protocols'] as List?) ?? []).map((e) => '$e').toList();

  bool get isLive => raw['status'] == 'live';
  bool get simulated => raw['simulated'] == true;
  String get operator => '${raw['operator'] ?? ''}';
  String get location => '${raw['location'] ?? ''}';
  String get purpose => '${raw['purpose'] ?? ''}';
  DateTime? get updatedAt => DateTime.tryParse('${raw['updated_at'] ?? ''}')?.toLocal();
  DateTime? get startedAt => DateTime.tryParse('${raw['started_at'] ?? ''}')?.toLocal();

  String get reference {
    final id = '${raw['session_id'] ?? this.id}';
    return id.length >= 13 ? 'MDK-${id.substring(2, 8)}-${id.substring(9, 13)}' : id;
  }

  String get brand {
    final b = '${machine['brand_name'] ?? ''}';
    final i = b.indexOf(' (');
    return i > 0 ? b.substring(0, i) : b;
  }

  String get model => '${machine['model'] ?? ''}';
  String get title => '$brand $model'.trim().isEmpty ? 'Máquina sin identificar' : '$brand $model'.trim();

  int get activeCount => (summary['active_dtcs'] as num?)?.toInt() ?? 0;
  int get maxSeverity => (summary['max_severity'] as num?)?.toInt() ?? 0;

  /// Índice de estado 0-100 (lo calcula el portátil; si falta, se estima aquí).
  int get health {
    final h = raw['health'];
    if (h is Map && h['score'] is num) return (h['score'] as num).round();
    var s = 100.0;
    for (final d in dtcs.where((d) => d['active'] == true)) {
      s -= const {5: 26, 4: 16, 3: 8, 2: 3, 1: 1}[(d['severity'] as num).toInt()] ?? 1;
    }
    s -= const {'manipulado': 22, 'sospechoso': 9}[tamper['verdict']] ?? 0;
    return s.clamp(0, 100).round();
  }

  String get healthLabel {
    final h = raw['health'];
    if (h is Map && h['label'] != null) return '${h['label']}';
    final s = health;
    return s >= 85 ? 'Óptimo' : s >= 65 ? 'Aceptable' : s >= 40 ? 'Requiere atención' : 'Crítico';
  }

  Duration? get duration {
    final a = startedAt, b = updatedAt;
    if (a == null || b == null) return null;
    return b.difference(a);
  }
}

/// Cómo se muestra cada medida: unidad de taller, decimales y rangos.
class Measure {
  final String key, label, unit;
  final double factor;   // conversión desde la unidad del portátil
  final int decimals;
  final double min, max; // escala del instrumento
  final double? lo, hi;  // zona normal
  const Measure(this.key, this.label, this.unit, {this.factor = 1, this.decimals = 1, required this.min,
      required this.max, this.lo, this.hi});

  double convert(num v) => v * factor;
  bool isLow(double v) => lo != null && v < lo!;
  bool isHigh(double v) => hi != null && v > hi!;
}

const measures = <String, Measure>{
  'rpm': Measure('rpm', 'Régimen motor', 'rpm', decimals: 0, min: 0, max: 2500, lo: 650, hi: 2250),
  'oil_pressure_kpa': Measure('oil_pressure_kpa', 'Presión de aceite', 'bar', factor: 0.01, decimals: 2,
      min: 0, max: 7, lo: 2.5, hi: 6.5),
  'coolant_c': Measure('coolant_c', 'Refrigerante', '°C', decimals: 2, min: 20, max: 120, lo: 70, hi: 100),
  'oil_temp_c': Measure('oil_temp_c', 'Aceite motor', '°C', decimals: 2, min: 20, max: 130, lo: 60, hi: 115),
  'hyd_oil_temp_c': Measure('hyd_oil_temp_c', 'Aceite hidráulico', '°C', decimals: 2, min: 10, max: 110, lo: 30, hi: 85),
  'trans_oil_temp_c': Measure('trans_oil_temp_c', 'Aceite transmisión', '°C', decimals: 2, min: 10, max: 130, lo: 40, hi: 105),
  'boost_kpa': Measure('boost_kpa', 'Sobrealimentación', 'bar', factor: 0.01, decimals: 2, min: 0, max: 3),
  'fuel_rate_lh': Measure('fuel_rate_lh', 'Consumo', 'L/h', decimals: 1, min: 0, max: 70),
  'battery_v': Measure('battery_v', 'Tensión batería', 'V', decimals: 2, min: 18, max: 32, lo: 24.5, hi: 29.5),
  'torque_pct': Measure('torque_pct', 'Par motor', '%', decimals: 0, min: 0, max: 100),
  'fuel_level_pct': Measure('fuel_level_pct', 'Combustible', '%', decimals: 1, min: 0, max: 100, lo: 12),
  'def_level_pct': Measure('def_level_pct', 'AdBlue', '%', decimals: 1, min: 0, max: 100, lo: 12),
  'intake_temp_c': Measure('intake_temp_c', 'Aire de admisión', '°C', decimals: 1, min: 0, max: 90, hi: 70),
  'ambient_c': Measure('ambient_c', 'Ambiente', '°C', decimals: 1, min: -20, max: 50),
  'oil_level_pct': Measure('oil_level_pct', 'Nivel de aceite', '%', decimals: 0, min: 0, max: 100, lo: 60),
  'coolant_level_pct': Measure('coolant_level_pct', 'Nivel refrigerante', '%', decimals: 0, min: 0, max: 100, lo: 60),
  'fuel_temp_c': Measure('fuel_temp_c', 'Combustible (temp.)', '°C', decimals: 1, min: 0, max: 90, hi: 70),
  'speed_kmh': Measure('speed_kmh', 'Velocidad', 'km/h', decimals: 0, min: 0, max: 120),
  'load_pct': Measure('load_pct', 'Carga motor', '%', decimals: 0, min: 0, max: 100),
};

Measure measureFor(String key, Map p) => measures[key] ??
    Measure(key, '${p['label'] ?? key}', '${p['unit'] ?? ''}', min: 0, max: 100);

num? asNum(dynamic v) => v is num ? v : num.tryParse('$v');

/// 9876.5 → "9.876,5" (formato español, cifras tabulares).
String fmtNum(dynamic v, {int decimals = 1}) {
  final n = asNum(v);
  if (n == null) return '—';
  final s = n.toDouble().toStringAsFixed(decimals);
  final neg = s.startsWith('-');
  final parts = (neg ? s.substring(1) : s).split('.');
  final buf = StringBuffer();
  for (var i = 0; i < parts[0].length; i++) {
    if (i > 0 && (parts[0].length - i) % 3 == 0) buf.write('.');
    buf.write(parts[0][i]);
  }
  return '${neg ? '−' : ''}$buf${decimals > 0 ? ',${parts[1]}' : ''}';
}

String euros(dynamic a, dynamic b) => '${fmtNum(a, decimals: 0)} – ${fmtNum(b, decimals: 0)} €';

const _months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
  'noviembre', 'diciembre'];
const _days = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

String hhmm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
String longDate(DateTime d) => '${_days[d.weekday - 1]}, ${d.day} de ${_months[d.month - 1]}';

String whenText(DateTime? d) {
  if (d == null) return '';
  final now = DateTime.now();
  final diff = DateTime(now.year, now.month, now.day).difference(DateTime(d.year, d.month, d.day)).inDays;
  if (diff == 0) return 'Hoy, ${hhmm(d)}';
  if (diff == 1) return 'Ayer, ${hhmm(d)}';
  return '${d.day} ${_months[d.month - 1].substring(0, 3)}, ${hhmm(d)}';
}

String durText(Duration? d) {
  if (d == null) return '';
  final m = d.inMinutes;
  return m < 60 ? '$m min' : '${m ~/ 60} h ${m % 60} min';
}
