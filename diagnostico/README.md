# Horken · Diagnóstico de maquinaria pesada

Sistema interno: el portátil lee la máquina (J1939/CAN), lo analiza y lo sube a Firebase;
en el móvil (Alemania) y en el del mecánico (España) se ve lo mismo **en tiempo real**.
El informe PDF se envía por email a los correos que elijáis.

```
[Máquina] ─ Deutsch 9 pines ─ [Adaptador CAN] ─ USB ─ [Portátil: motor_python]
                                                        │
                                                 Firebase Firestore
                                                  │               │
                                         [Móvil Alemania]   [Móvil España]
```

| Carpeta | Qué es |
|---|---|
| `motor_python/` | Programa del portátil: lectura J1939, base de averías, detección de manipulación, PDF, email, simulador |
| `app_flutter/` | App Android (y web) para ti y tu mecánico |
| `firebase/firestore.rules` | Reglas: solo vuestros dos correos pueden entrar |
| `docs/` | Capturas e informe PDF de ejemplo |

## 1. Probar YA, sin adaptador (Mac)

```bash
cd diagnostico/motor_python
python3 -m pip install -r requirements.txt
python3 -m horken_diag demo --escenario cat320 --segundos 20   # Caterpillar con horas rebajadas
python3 -m horken_diag demo --escenario arjes --segundos 20    # Arjes con centralita de otra máquina
python3 -m horken_diag demo --escenario hamm --segundos 20     # Hamm sin manipulación
python3 -m pytest -q                                           # 12 pruebas automáticas
```
Genera `sesiones/<id>.json` y `sesiones/<id>.pdf`.

La app sin Firebase arranca en **modo demostración** con esos mismos datos:
```bash
cd diagnostico/app_flutter
flutter run -d chrome        # o con el móvil Android conectado: flutter run
```

## 2. Adaptador (cuando decidas comprar)

Funciona en **Mac**, no hace falta Windows:

| Adaptador | Precio aprox. | Mac | Comando |
|---|---|---|---|
| PEAK PCAN-USB | 200–300 € | Sí (driver PCBUSB de mac-can.com) | `leer --interfaz pcan --canal PCAN_USBBUS1` |
| CANable 2 / candleLight | 40–90 € | Sí | `leer --interfaz slcan --canal /dev/tty.usbmodemXXXX` |
| Cable Deutsch 9 pines → DB9 (J1939) | 25–60 € | — | imprescindible con cualquiera de los dos |

Los adaptadores "RP1210" (Nexiq, Cat Comm Adapter) solo funcionan en Windows.

```bash
python3 -m horken_diag leer --interfaz pcan --canal PCAN_USBBUS1 --bitrate 250000 --clase excavadora_20t
```
Clases: `excavadora_20t, excavadora_grande, cargadora_ruedas, dumper_articulado, bulldozer, rodillo, trituradora, retro_mixta, minicargadora, camion`.
El programa **solo lee**. No escribe nada en las centralitas.

## 3. Firebase (gratis, plan Spark)

1. https://console.firebase.google.com → Crear proyecto "horken".
2. **Firestore Database** → Crear → modo producción. Pegar en *Reglas* el contenido de `firebase/firestore.rules` con vuestros dos correos.
3. **Authentication** → Correo/contraseña → crear los usuarios para ti y para tu mecánico.
4. Clave del portátil: Configuración del proyecto → Cuentas de servicio → *Generar nueva clave privada* → guardarla como `motor_python/clave-servicio-firebase.json` (**no compartirla**).
5. App: `dart pub global activate flutterfire_cli` y en `app_flutter/` ejecutar `flutterfire configure` (sustituye `lib/firebase_options.dart`).
6. Copiar `motor_python/config.ejemplo.json` a `config.json` y rellenarlo.

Consumo: con un envío cada 2 s son unas 1.800 escrituras por hora de diagnóstico. El límite gratuito es de 20.000 al día (unas 10 h de lectura diarias).

## 4. Email (gratis)

Lo envía el portátil por Gmail. Así no hace falta el plan de pago de Firebase.
Cuenta de Google → Seguridad → Verificación en 2 pasos → **Contraseñas de aplicación** → crear una y ponerla en `config.json`.
Desde la app, pestaña *Informe*: añadir correos → *Enviar informe*. El portátil genera el PDF y lo envía.

## 5. Android solo para testers

`flutter build appbundle` → Play Console → *Pruebas internas* → añadir vuestros correos como testers (sin publicar).
O directamente `flutter build apk` e instalar el APK en los dos móviles.

## Qué hace y qué no (honestamente)

- **Averías de todas las centralitas** que hablan J1939: motor, postratamiento, transmisión, cuadro y controladores del fabricante (DM1 activas, DM2 históricas).
- **Base de averías** con causas, pasos, piezas, coste orientativo y dificultad del 1 al 5. Incluye los SPN estándar más frecuentes y se amplía con cada reparación (`horken_diag/kb/spn.json`).
- **Horas/km manipulados**: cruza horas entre centralitas, revoluciones totales, gasoil total, km y revisiones anteriores. Da un nivel de sospecha con las pruebas, no una certeza.
- **Modificaciones**: detecta centralitas de otra máquina, cambios de software entre revisiones e identificadores no originales. Una reprogramación profesional puede no dejar rastro.
- **Códigos propietarios** (eventos Cat E###, controladores Hamm/Arjes): se muestran como "propietario". Su significado exacto está en el software oficial de cada marca.
- Los **costes** son rangos orientativos. Verificar siempre la referencia por número de serie.
