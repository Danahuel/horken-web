/// Envoltorio cómodo sobre el documento de Firestore `sessions/{id}`,
/// que escribe el programa Python del portátil.
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
  Map<String, dynamic> get reportStatus => _m('report_status');
  List<Map<String, dynamic>> get dtcs => _l('dtcs');
  List<Map<String, dynamic>> get ecus => _l('ecus');
  List<String> get recipients => ((raw['recipients'] as List?) ?? []).map((e) => '$e').toList();

  List<String> get protocols => ((raw['protocols'] as List?) ?? []).map((e) => '$e').toList();
  String get shortId {
    final id = '${raw['session_id'] ?? this.id}';
    return id.length >= 13 ? '${id.substring(4, 8)}-${id.substring(9, 13)}' : id;
  }

  bool get isLive => raw['status'] == 'live';
  bool get simulated => raw['simulated'] == true;
  String get operator => '${raw['operator'] ?? ''}';
  String get location => '${raw['location'] ?? ''}';
  DateTime? get updatedAt => DateTime.tryParse('${raw['updated_at'] ?? ''}')?.toLocal();

  String get title {
    final m = machine;
    final t = '${m['brand_name'] ?? ''} ${m['model'] ?? ''}'.trim();
    return t.isEmpty ? 'Máquina sin identificar' : t;
  }

  int get activeCount => (summary['active_dtcs'] as num?)?.toInt() ?? 0;
  int get maxSeverity => (summary['max_severity'] as num?)?.toInt() ?? 0;
}

num? asNum(dynamic v) => v is num ? v : num.tryParse('$v');

String fmtNum(dynamic v, {int decimals = 1}) {
  final n = asNum(v);
  if (n == null) return '—';
  final s = n.toStringAsFixed(decimals);
  final parts = s.split('.');
  final buf = StringBuffer();
  final digits = parts[0].replaceAll('-', '');
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) buf.write('.');
    buf.write(digits[i]);
  }
  final sign = parts[0].startsWith('-') ? '-' : '';
  return decimals > 0 ? '$sign$buf,${parts[1]}' : '$sign$buf';
}

const _months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

String hhmm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// "hoy 09:41", "ayer 18:02", "3 nov 10:15"
String whenText(DateTime? d) {
  if (d == null) return '';
  final now = DateTime.now();
  final day = DateTime(d.year, d.month, d.day);
  final diff = DateTime(now.year, now.month, now.day).difference(day).inDays;
  if (diff == 0) return 'hoy ${hhmm(d)}';
  if (diff == 1) return 'ayer ${hhmm(d)}';
  return '${d.day} ${_months[d.month - 1]}${d.year != now.year ? ' ${d.year}' : ''} ${hhmm(d)}';
}

String euros(dynamic a, dynamic b) => '${fmtNum(a, decimals: 0)}–${fmtNum(b, decimals: 0)} €';
