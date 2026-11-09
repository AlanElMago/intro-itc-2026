# Demo Jerarquía de Memoria V2

Tres procesos encadenados (cifrar → descifrar + comprimir → descomprimir) que comparten datos por:

| Modo | Dónde viajan los datos | Sincronización |
|---|---|---|
| `disco` | Archivos en `shared_disk_memory/` (mmap) | Ejecución secuencial + `Lock` |
| `ram` | Segmento de memoria compartida creado con **kax** | Semáforos |
| `nube` | Archivos en **Google Drive**; el ID de cada archivo se pasa por RAM (kax) | Semáforos |

## 1. Instalar dependencias
```bash
pip install -r requirements.txt
```

## 2. Crear archivo de entrada
```bash
python config.py
```

## Repeticiones
Todos los modos aceptan un segundo argumento opcional con el número de repeticiones (por defecto 1).
Al final se muestra la **media** y la **mediana** de dos tiempos:
```bash
python main.py ram 10
```

| Tiempo | Qué incluye |
|---|---|
| **Transferencias** | Solo escribir y leer en el medio compartido: P1→P2 (`cifrado`) y P2→P3 (`comprimido`). En disco: escribir + `mmap.flush()` y leer con `mmap`. En RAM: escribir/leer el segmento con kax (incluye su base64). En nube: subir/descargar de Drive + pasar el ID por kax. |
| **Total** | Todo: crear procesos, leer la entrada, cifrar, comprimir, esperas en semáforos y escribir la salida final. |

## Archivo de entrada (variable de entorno `DEMO_INPUT`)

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `DEMO_INPUT` | `input/documento_secreto.txt` | Ruta del archivo que procesan los 3 procesos. El valor por defecto es el archivo de 3 KB que genera `python config.py`. |

Admite rutas absolutas o relativas a la carpeta desde donde ejecutas la demo.

```bash
# Solo para un comando
DEMO_INPUT=/mnt/d/images.zip python main.py disco 5

# Para toda la sesión de la terminal
export DEMO_INPUT=/mnt/d/images.zip
python main.py ram 3

# Volver al archivo por defecto
unset DEMO_INPUT
```

- La salida conserva la extensión de la entrada: `output_final/archivo_recuperado_<modo>.zip`.
- El segmento de RAM compartida se dimensiona según el tamaño del archivo.
- El archivo por defecto solo se genera automáticamente cuando no defines `DEMO_INPUT`.
- Si la ruta de `DEMO_INPUT` no existe, la demo se detiene con un mensaje indicándolo.

## 3. Modo DISCO
```bash
python main.py disco
```
Salida: `output_final/archivo_recuperado_disco.<ext>`

## 4. Modo RAM (kax)
```bash
python main.py ram
```
Salida: `output_final/archivo_recuperado_ram.<ext>`

Solo se usan las funciones locales de kax (`makeShm`, `putDataToShm`, `getDataFromShm`, `removeShm`); no hace falta el servidor ESS.

## 5. Modo NUBE (Google Drive)

### Archivos requeridos

| Archivo | Para qué sirve | Cómo se obtiene |
|---|---|---|
| `credentials.json` | Identifica la app ante Google (OAuth client ID) | Lo descargas tú de Google Cloud Console (pasos abajo) |
| `token.json` | Guarda tu autorización para no abrir el navegador cada vez | Se crea solo la primera vez que ejecutas `python main.py nube` y autorizas |

Ambos van en esta carpeta (`DemoMemoryHerarchyV2/`).

### Cómo conseguir `credentials.json` (una sola vez)
1. Entra a [Google Cloud Console](https://console.cloud.google.com/) y crea un proyecto (o elige uno).
2. **APIs y servicios → Biblioteca** → busca **Google Drive API** → **Habilitar**.
3. **APIs y servicios → Pantalla de consentimiento de OAuth**:
   - Tipo de usuario: **Externo**.
   - Rellena nombre de la app y tu correo.
   - En **Usuarios de prueba**, añade tu cuenta de Gmail.
4. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:
   - Tipo de aplicación: **App de escritorio** (⚠️ no "Aplicación web": falla con `redirect_uri_mismatch`).
5. **Descargar JSON** y guárdalo en esta carpeta con el nombre `credentials.json`
   (o déjale el nombre original y usa `GDRIVE_CREDENTIALS=<archivo>.json`).

Comprobación rápida: el JSON correcto empieza con `{"installed": ...}`; si empieza con `{"web": ...}` es el tipo equivocado.

### Ejecución
```bash
python main.py nube
```
La primera vez se abre el navegador para autorizar (en WSL, copia la URL que aparece en la terminal y ábrela en Windows).
Si aparece "Google no ha verificado esta app", pulsa **Configuración avanzada → Ir a … (no seguro)**. Al terminar se crea `token.json`.

### ¿Hay que autorizar cada vez?
No. `token.json` se renueva solo. Excepciones:
- Mientras la app esté en modo **Prueba**, Google invalida el token a los **7 días** y la demo vuelve a abrir el navegador. Para evitarlo: **Pantalla de consentimiento de OAuth → Publicar app**.
- Si borras `token.json` o revocas el acceso en tu cuenta de Google.

Salidas:
- `cifrado.bin` y `comprimido.zip` en la carpeta de Drive `DemoMemoryHerarchyV2`
- `output_final/archivo_recuperado_nube.<ext>`

Variables de entorno opcionales: `GDRIVE_CREDENTIALS`, `GDRIVE_TOKEN`, `GDRIVE_FOLDER`.

> `credentials.json` y `token.json` dan acceso a tu Drive: no los subas a ningún repositorio.
>
> ⚠️ `comprimido.zip` se sube a Drive **sin cifrar**. No uses el modo nube con datos sensibles (p. ej. imágenes de pacientes).

## 6. Limpieza opcional
```bash
rm -f shared_disk_memory/*.bin shared_disk_memory/*.zip output_final/archivo_recuperado_*
```
Los archivos de Drive se borran a mano desde la carpeta `DemoMemoryHerarchyV2`.
