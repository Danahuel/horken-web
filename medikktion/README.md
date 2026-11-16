# Medikktion · Diagnóstico de maquinaria pesada

> **¿Primera vez? Sigue [GUIA.md](GUIA.md) paso a paso.**

Sistema interno: el portátil lee la máquina (J1939/CAN), lo analiza y lo sube a Firebase;
en el móvil (Alemania) y en el del mecánico (España) se ve lo mismo **en tiempo real**.
El informe PDF se envía por email a los correos que elijáis.

```
[Máquina] ─ Deutsch 9 pines ─ [Lector CAN] ─ USB ─ [Portátil]
                                                        │
                                                 Firebase Firestore
                                                  │               │
                                         [Móvil Alemania]   [Móvil España]
```

| Carpeta | Qué es |
|---|---|
| `portatil/` | Programa del portátil: lectura J1939, base de averías, detección de manipulación, PDF, email, simulador |
| `app/` | App Android (y web) para ti y tu mecánico |
| `firebase/firestore.rules` | Reglas: solo vuestros dos correos pueden entrar |
| `docs/` | Capturas e informe PDF de ejemplo |
| `GUIA.md` | Montaje paso a paso (Windows, Firebase, Gmail, móviles) |

## La app

Diseño grafito y oro champán (tema claro "porcelana" para trabajar al sol). Cada máquina tiene:

- **Resumen**: índice de estado 0–100, testigos, integridad del horómetro con el registro de cada centralita,
  prioridades y ficha técnica.
- **Medidas**: esferas con aguja (régimen, presión de aceite), termómetros (refrigerante, aceite motor,
  hidráulico, transmisión) y tendencias de los últimos 15 minutos con mínimo, media, máximo y línea de alarma.
  Los valores se interpolan suavemente entre lecturas, con dos decimales.
- **Averías**: gravedad, causas, procedimiento, piezas, presupuesto y dificultad 1–5.
- **Centralitas**: software, calibraciones (DM19), horómetros y contadores.
- **Informe**: destinatarios y envío del PDF.

Demostración incluida (botón *Ver demostración*): Caterpillar 320 con horómetro manipulado, Fuchs MHL350,
Arjes VZ950 con centralita de otra máquina y Hamm H13i en buen estado. Se regeneran con
`python -m medikktion generar-demos`.

## Cómo viaja la información

1. **Máquina → portátil (cable):** lector RP1210 en el conector de diagnóstico, USB al portátil. Solo lectura.
2. **Portátil → nube (internet, normalmente la zona Wi-Fi del móvil):** cada 2 s se sube el estado completo
   de la máquina a Firestore con la clave de servicio.
3. **Nube → móviles:** la app está suscrita al documento y recibe cada cambio al instante (< 1 s).
4. **Vuelta:** "Enviar informe" en la app → el portátil genera el PDF y lo manda por Gmail.

**A prueba de cortes:** la subida va en un hilo aparte con reintentos (2 → 60 s), copia local cada 5 s,
sesiones terminadas sin conexión en `sesiones/pendientes/` (se suben al arrancar o con
`python -m medikktion subir-pendientes`), informes en espera, y aviso **SIN SEÑAL** en la app si el portátil
deja de enviar más de 20 s. Probar el aviso en la demo web: añadir `?corte=1` a la dirección.

## Protocolos y bibliotecas

| Protocolo | Para qué máquinas | Biblioteca | Lector |
|---|---|---|---|
| **SAE J1939** (DM1/DM2/DM19, contadores, en vivo) | Maquinaria pesada y camiones modernos: Caterpillar, Fuchs, Hamm, Arjes, Liebherr, Volvo, Komatsu... | python-can + propia | RP1210, PCAN, CANable, Kvaser |
| **UDS** ISO 14229 sobre ISO-TP | Centralitas modernas de máquina, camión y coche | udsoncan + can-isotp | los mismos |
| **J1708 / J1587** | Máquinas y camiones anteriores a ~2005 | propia, vía RP1210 | RP1210 |
| **OBD-II** | Coches y furgonetas | python-OBD (+2.000 códigos SAE) | ELM327 |
| **DBC** del fabricante | Mensajes propietarios de una marca concreta | cantools | — |

Base de averías: 98 SPN con causas, pasos, piezas, precio y dificultad; 32 perfiles de marca;
códigos genéricos P/C/B/U con descripción oficial SAE.

## 1. Probar YA, sin adaptador (Windows o Mac)

```bash
cd medikktion/portatil
python3 -m pip install -r requirements.txt
python3 -m medikktion demo --escenario cat320 --segundos 20   # Caterpillar con horas rebajadas
python3 -m medikktion demo --escenario arjes --segundos 20    # Arjes con centralita de otra máquina
python3 -m medikktion demo --escenario hamm --segundos 20     # Hamm sin manipulación
python3 -m medikktion demo --escenario fuchs --segundos 20    # Fuchs MHL: J1939 + controlador UDS
python3 -m pytest -q                                           # 28 pruebas automáticas
```
En Windows usa `py` en lugar de `python3`, o directamente `diagnostico.bat` → opción 3.
Genera `sesiones/<id>.json` y `sesiones/<id>.pdf`.

La app sin Firebase arranca en **modo demostración** con esos mismos datos:
```bash
cd medikktion/app
flutter run -d chrome        # o con el móvil Android conectado: flutter run
```

## 2. Portátil Windows + lector RP1210 (opción elegida)

**Lector recomendado:** cualquiera compatible con **RP1210** (el estándar de diagnóstico de pesados en Windows):

| Lector | Precio aprox. | Notas |
|---|---|---|
| Kit "USB-Link 2" compatible (clon de Nexiq 125032) | 80–200 € | Suele traer cables Deutsch de 9 pines (negro 250k y verde 500k), 6 pines y OBD2. Calidad variable: instalar solo el driver |
| NEXIQ USB-Link 2/3 original | 800–1.100 € | Profesional, el más compatible |
| DG Technologies DPA5 | 900–1.200 € | Profesional |

Ventaja de Windows: el mismo lector sirve en el futuro para el software oficial (Cat ET, Deutz SerDia, etc.) si compras licencia.

**Instalación (una sola vez):**
1. Instalar el driver del lector (crea `C:\Windows\RP121032.ini`).
2. Instalar Python desde python.org y marcar *Add python.exe to PATH*.
   Si el lector solo trae DLL de 32 bits (lo sabrás porque el programa te lo dirá), instala **Python de 32 bits (Windows installer x86)**.
3. Doble clic en `portatil\instalar_windows.bat`.

**Uso:** doble clic en `portatil\diagnostico.bat` → opción 1. Por línea de comandos:
```bat
py -m medikktion adaptadores
py -m medikktion leer --interfaz rp1210 --canal NULN2R32 --dispositivo 1 --bitrate 0 --clase excavadora_20t
```
`--bitrate 0` detecta la velocidad automáticamente. Si el lector no admite CAN en bruto, añade `--protocolo J1939`.

Otros lectores que también funcionan (Windows y Mac): PEAK PCAN-USB (`--interfaz pcan`), CANable (`--interfaz slcan`), Kvaser (`--interfaz kvaser`).
El programa **solo lee**. No escribe nada en las centralitas.

## 3. Firebase y Gmail: asistente automático

`python -m medikktion configurar` (o `diagnostico.bat` → 6) crea la base de datos, las cuentas,
las reglas de seguridad, registra la app y os envía por email el código de la app y la contraseña.
`python -m medikktion comprobar` revisa que todo funcione. Detalle manual (por si el asistente no puede):

### Firebase a mano (gratis, plan Spark)

1. https://console.firebase.google.com → Crear proyecto "medikktion".
2. **Firestore Database** → Crear → modo producción. Pegar en *Reglas* el contenido de `firebase/firestore.rules` con vuestros dos correos.
3. **Authentication** → Correo/contraseña → crear los usuarios para ti y para tu mecánico.
4. Clave del portátil: Configuración del proyecto → Cuentas de servicio → *Generar nueva clave privada* → guardarla como `portatil/clave-servicio-firebase.json` (**no compartirla**).
5. App: registrar app Android `com.medikktion.medikktion`, descargar `google-services.json` y ejecutar
   `python -m medikktion codigo-app google-services.json`: el código `MDK1:...` se pega en la app.
6. Copiar `portatil/config.ejemplo.json` a `config.json` y rellenarlo.

Consumo: con un envío cada 2 s son unas 1.800 escrituras por hora de diagnóstico. El límite gratuito es de 20.000 al día (unas 10 h de lectura diarias).

## 4. Email (gratis)

Lo envía el portátil por Gmail. Así no hace falta el plan de pago de Firebase.
Cuenta de Google → Seguridad → Verificación en 2 pasos → **Contraseñas de aplicación** → crear una y ponerla en `config.json`.
Desde la app, pestaña *Informe*: añadir correos → *Enviar informe*. El portátil genera el PDF y lo envía.

## 5. App Android

No hace falta instalar Flutter: **GitHub compila el APK solo** en cada cambio
(pestaña *Actions* → última ejecución → *Artifacts* → `Medikktion-android`).
El mismo APK vale para cualquier proyecto Firebase: se configura pegando el código `MDK1:...`.
Para Google Play (prueba interna): `flutter build appbundle` con una clave de subida propia.

## Qué hace y qué no (honestamente)

- **Averías de todas las centralitas** que hablan J1939: motor, postratamiento, transmisión, cuadro y controladores del fabricante (DM1 activas, DM2 históricas).
- **Base de averías** con causas, pasos, piezas, coste orientativo y dificultad del 1 al 5. Incluye los SPN estándar más frecuentes y se amplía con cada reparación (`medikktion/kb/spn.json`).
- **Horas/km manipulados**: cruza horas entre centralitas, revoluciones totales, gasoil total, km y revisiones anteriores. Da un nivel de sospecha con las pruebas, no una certeza.
- **Modificaciones**: detecta centralitas de otra máquina, cambios de software entre revisiones e identificadores no originales. Una reprogramación profesional puede no dejar rastro.
- **Códigos propietarios** (eventos Cat E###, controladores Hamm/Arjes): se muestran como "propietario". Su significado exacto está en el software oficial de cada marca.
- Los **costes** son rangos orientativos. Verificar siempre la referencia por número de serie.


## Mover a un repositorio propio

Esta carpeta es autónoma. Para llevarla a un repositorio nuevo (por ejemplo `medikktion`):

1. Crear el repositorio vacío en GitHub.
2. Copiar **el contenido** de esta carpeta a la raíz del repositorio nuevo (incluida la carpeta oculta `.github`).
3. Subirlo. El archivo `.github/workflows/medikktion.yml` de esta carpeta ya está preparado para esa
   estructura: compila el APK y pasa las pruebas en cada cambio.
