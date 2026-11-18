# Guía de montaje — Medikktion

Sigue los pasos en orden. Cuando estés delante del ordenador, abre esta guía y dime en qué paso estás:
te acompaño en cada uno. Si algo sale distinto a lo que pone aquí, mándame una foto de la pantalla.

**Tiempo total aproximado:** 45–60 minutos la primera vez.
**Necesitas:** el portátil Windows, tu móvil Android, tu cuenta de Gmail y conexión a internet.

---

## Paso 1 · Descargar el programa en el portátil (5 min)

1. En el portátil, abre el repositorio de Medikktion en GitHub.
2. Botón verde **Code** → **Download ZIP**.
3. Descomprime el ZIP en `C:\Medikktion` (clic derecho → Extraer todo).
   El programa del portátil queda en la carpeta `portatil`.

## Paso 2 · Instalar Python (5 min)

1. https://www.python.org/downloads/windows/ → descarga **Python 3.12** ("Windows installer 64-bit").
2. Al instalar, **marca la casilla "Add python.exe to PATH"** (abajo del todo) → *Install Now*.
3. Abre la carpeta `portatil` y haz **doble clic en `instalar_windows.bat`**.
   Tarda unos minutos. Al final verás "Listo".

> Si más adelante, con el lector conectado, el programa dice que la DLL "no es de 64 bits",
> desinstala Python e instala el de **32 bits** ("Windows installer (32-bit)"). Te avisaré si hace falta.

## Paso 3 · Probar sin máquina (2 min)

El instalador deja un icono **Medikktion** en el escritorio (si no aparece: doble clic en `portatil\Medikktion.bat`).
Se abre la **estación de lectura**: una ventana negra y amarilla con todo lo necesario.

1. Arriba a la izquierda, pestaña **PRUEBA** → elige una máquina simulada.
2. Botón amarillo **EMPEZAR LECTURA**. Verás la máquina, sus averías y los valores moviéndose.
3. **PARAR LECTURA**: queda en el **Libro de lecturas** con su informe PDF.

**Si esto funciona, el programa está bien instalado.** (El menú de texto `diagnostico.bat` sigue disponible
como alternativa.)

## Paso 4 · Crear el proyecto de Firebase (10 min)

1. Entra en https://console.firebase.google.com con tu cuenta de Google.
2. **Crear un proyecto** → nombre `medikktion` → desactiva Google Analytics (no hace falta) → Crear.
3. Plan: deja el gratuito (**Spark**). No metas tarjeta.
4. Rueda dentada ⚙ (arriba a la izquierda) → **Configuración del proyecto** → pestaña **Cuentas de servicio**
   → botón **Generar nueva clave privada** → Generar clave.
   Se descarga un archivo `.json`. **Ese archivo es la llave de tu base de datos: no se lo mandes a nadie.**

El resto (base de datos, usuarios, reglas de seguridad, registrar la app) lo hace el asistente en el paso 6.

## Paso 5 · Contraseña de aplicación de Gmail (5 min)

Sirve para que el portátil pueda enviar los informes desde tu Gmail.

1. https://myaccount.google.com/security → activa la **Verificación en dos pasos** si no la tienes.
2. https://myaccount.google.com/apppasswords → nombre: `Medikktion` → **Crear**.
3. Te da 16 letras (tipo `abcd efgh ijkl mnop`). Déjalas en pantalla: las pegas en el paso 6.

## Paso 6 · Asistente de configuración (5 min)

Doble clic en `diagnostico.bat` → opción **6 (Configurar)**. Te irá preguntando:

| Pregunta | Qué pones |
|---|---|
| Ruta del archivo de clave | Arrastra el `.json` del paso 4 a la ventana y pulsa Enter |
| Tu nombre | Como quieras que salga en los informes |
| Tu email | Tu Gmail |
| Email y nombre de tu mecánico | Los suyos |
| Contraseña de aplicación | Las 16 letras del paso 5 (no se ven al pegar, es normal) |
| Tarifa €/h | Lo que cobra tu taller por hora (por defecto 55) |

Al terminar verás una lista con `[ OK ]`. Lo que salga con `[ !! ]` lo explica abajo: son 1 o 2 clics en la
consola de Firebase. Después vuelve a ejecutar la opción 6.

**Resultado:** a ti y a tu mecánico os llega un email "Medikktion · tu acceso" con:
- el **código de la app** (una línea que empieza por `MDK1:`)
- vuestra **contraseña**

Comprueba todo con `diagnostico.bat` → opción **5 (Comprobar)**: todo en `[ OK ]`.

## Paso 7 · Instalar la app en los móviles (5 min cada uno)

1. Descarga `Medikktion.apk`: en GitHub → pestaña **Actions** → la última ejecución con ✓ verde
   → abajo, en *Artifacts*, **Medikktion-android** (descarga un ZIP con el APK dentro).
   (O te lo paso yo directamente.)
2. Pásalo al móvil (WhatsApp a ti mismo, cable o Drive) y ábrelo.
   Android preguntará si permites instalar apps de esa fuente → **Permitir**.
3. Abre Medikktion → **pega el código** `MDK1:...` del email → *Activar*.
4. Entra con tu email y la contraseña del email.
5. Tu mecánico hace lo mismo en España con su email.

> Más adelante, si quieres, se sube a Google Play como "prueba interna" (solo vosotros dos). No es necesario.

## Paso 8 · Prueba de tiempo real Alemania ↔ España (2 min)

1. En el portátil: **Medikktion** → **PRUEBA** → Caterpillar 320 → **EMPEZAR LECTURA**.
2. En tu móvil y en el de tu mecánico aparece **CATERPILLAR 320 · en directo**, y los valores se mueven a la vez.
3. En la app → pestaña **Informe** → *Enviar informe*. En unos segundos llega el PDF.

**Si esto funciona, el sistema está montado.** Solo falta el lector.

## Paso 9 · El lector (cuando lo tengas)

1. Instala el driver/software que venga con el lector (solo el driver).
2. Abre **Medikktion**: en la pestaña **MÁQUINA**, el desplegable **Lector** debe mostrar el lector instalado.
3. Conecta el cable al conector de diagnóstico de la máquina (Deutsch 9 pines, suele estar en cabina),
   da el contacto (no hace falta arrancar), elige tipo de máquina y lugar, activa **Grabar todas las tramas**
   y pulsa **EMPEZAR LECTURA**. Arriba se encienden las luces **LECTOR** y **BUS CAN**.
5. Escribe los **km de desplazamiento** (solo ida) para que el presupuesto incluya el viaje, y si es una compra,
   el **precio que piden** en Datos de la placa: el informe calculará la oferta máxima.
6. Recomendado: abre **Datos de la placa** y apunta marca, modelo, nº de serie de la placa, año y las
   **horas que marca el cuadro**. No es obligatorio (la máquina suele identificarse sola), pero con ellos el
   programa comprueba además: que la centralita es de esa máquina, que el cuadro y la centralita dicen lo mismo
   y si las horas son normales para su edad.
4. Escribe el nombre del lector, el tipo de máquina y la ciudad. Los datos aparecen en los móviles.

Para coches y furgonetas: lector **ELM327** (USB o Bluetooth) → opción **2**.

---

### Grabar una máquina para analizarla después (pruebas reales)

En las primeras pruebas con máquinas reales, **graba siempre**:

- En el portátil: al elegir la opción 1, responde **s** a "¿Grabar todas las tramas?".
- O desde la app (tú o tu mecánico): pestaña **Centralitas** → interruptor **Grabar tramas CAN**.
  Arriba aparece **● REC** con el tamaño.

El archivo queda en `portatil\sesiones\grabaciones\` (formato BLF, 5–10 MB por hora).
Si algo no sale bien, mándame ese archivo: reproduzco la máquina tal cual y lo corrijo.
Para verla tú mismo otra vez: `diagnostico.bat` → opción **7 (Reproducir una grabación)**.
Las grabaciones se borran solas a los 90 días o si pasan de 2 GB.

### Si se corta internet durante una lectura

No pasa nada, sigue trabajando:

- El portátil **sigue leyendo y guardando** en su disco (carpeta `sesiones`). En pantalla verás
  `SIN CONEXIÓN … (guardando en el portátil)`.
- En los móviles, la máquina pasa a **SIN SEÑAL · hora del último dato**.
- Cuando vuelve la conexión, se sube todo solo, incluidas las mediciones de los últimos 15 minutos,
  y la app avisa con **Conexión recuperada**.
- Si pediste un informe sin conexión, se envía en cuanto vuelve.
- Si terminas la lectura sin conexión, la sesión queda pendiente y se sube sola la próxima vez que abras el
  programa (o a mano: `py -m medikktion subir-pendientes`).

### Espacio en el portátil

Cada lectura ocupa unos 150 KB (datos + PDF): 1.000 lecturas ≈ 150 MB. Aun así hay un límite automático:
al empezar cada lectura se borran del portátil las de **más de 365 días** o lo que pase de **1 GB**
(empezando por las más antiguas). Lo pendiente de subir no se borra nunca, y todo sigue en la app.
Se cambia en `config.json` (`retencion_dias`, `max_mb_local`).

### Si algo falla

| Síntoma | Qué hacer |
|---|---|
| "py no se reconoce" | Python no está instalado o no marcaste *Add to PATH* (paso 2) |
| `[FALLO] Gmail` | La contraseña de aplicación está mal copiada o falta la verificación en dos pasos |
| La app dice "código no válido" | Copia la línea `MDK1:` entera, sin espacios al principio |
| La app no muestra nada | Mira que el portátil diga "Firestore (los móviles lo ven ya)" al empezar |
| "La DLL no es de 64 bits" | Instala Python de 32 bits (paso 2) y vuelve a ejecutar `instalar_windows.bat` |
| 0 centralitas con la máquina | Contacto dado, cable bien encajado; prueba otra vez y mándame la pantalla |
